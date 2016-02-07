from flask import Flask, request, g, session, abort, \
                  redirect, make_response, url_for
from flask.templating import render_template
import oauth2
import sqlite3
import json
import urllib
import urlparse
import PyRSS2Gen as rss
import datetime
import cStringIO
from jinja2 import Template
import sys, os
import logging
from pprint import pformat
import hashlib
import base64

import config

app = Flask(__name__, template_folder='templates')
app.debug = True

with open(config.SECRET_KEY_PATH) as f:
    app.secret_key = f.read() 

CONSUMER_KEY = config.CONSUMER_KEY        # Tumblr API Consumer Key
CONSUMER_SECRET = config.CONSUMER_SECRET  # Tumblr API Consumer Secret

FEED_MAX = config.FEED_MAX

# Maximum number of posts per posts request to the tumblr API
TUMBLR_POST_LIMIT = 20

# Add 256 bits of randomness + 1 to make base64 work better
KEY_BYTES = (256 / 8) + 1

post_templates = {
    "text": """
    {{ body|safe }}
    """,

    "photo": """
    {%- for photo in photos -%}
        <img src="{{ photo.original_size.url }}" />
        {% if photo.caption %}<p>{{ photo.caption }}</p>{% endif %}
    {% endfor %}
    {% if caption %}<p>{{ caption }}</p>{% endif %}
    """,

    "quote": """
    <p>{{ text }}</p>
    {{ source|safe }}
    """,

    "link": """
    <a href="{{ url }}">
        {%- if title -%}
            {{ title }}
        {%- else -%}
            {{ url }}
        {% endif %}
    </a>
    {{ description|safe }}
    """,

    "chat": """
    {% for line in dialogue %}
        <p>{{ label }} {{ phrase }}</p>
    {% endfor %}
    """,

    "audio": """
    {{ player|safe }}
    {{ caption|safe }}
    """,

    "video": """
    {% set largest_player = player|sort(reverse=True, attribute='width')|first %}
    {{ largest_player.embed_code|safe }}
    {{ caption|safe }}
    """,

    "answer": """
    <p>Q: <a href="{{ asking_url }}">{{ asking_name }}</a></p>
    <blockquote>
        <p>{{ question }}</p>
    </blockquote>
    <p>A: <a href="{{ post_url }}">{{ blog_name }}</a></p>
    {{ answer|safe }}
    """

}

#Decorate the templates
for name, values in post_templates.iteritems():
    post_templates[name] = Template(post_templates[name])

@app.before_request
def setup():
    g.db = sqlite3.connect(config.USER_DB_PATH)
    g.c = g.db.cursor()

@app.teardown_request
def teardown(response):
    g.c.close()
    g.db.close()
    return response

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/register", methods=["GET"])
def register():
    consumer = oauth2.Consumer(CONSUMER_KEY, CONSUMER_SECRET)
    client = oauth2.Client(consumer)

    # According to spec one must be provided, however most
    # implementations could care less, Tumblr seems to respect this though...
    body = urllib.urlencode({"oauth_callback":
                             url_for("finish", _external=True)})

    resp, content = client.request("http://www.tumblr.com/oauth/request_token",
                                   "POST", body=body)
    if resp["status"] != "200": abort(400)

    session["request_token"] = dict(urlparse.parse_qsl(content))
    return redirect("http://www.tumblr.com/oauth/authorize?oauth_token={0}"\
                    .format(session["request_token"]["oauth_token"]))

def gen_hash():
    "Generate a one-time unique hash for the given user"
    key = os.urandom(KEY_BYTES)
    return base64.urlsafe_b64encode(key)

def remove_user(conn, curs, username):
    "Remove all entries pertaining to a user from the database"
    curs.execute("""DELETE FROM user where username = ?""", (username,))
    conn.commit()

def push_user(conn, curs, username, oauth_key, oauth_secret):
    remove_user(conn, curs, username)
    hash = gen_hash()
    curs.execute("""
        INSERT INTO user (version,hash,username,oauth_key,oauth_secret)
        VALUES (?,?,?,?,?)""",
        ("v2", hash, username, oauth_key, oauth_secret))
    conn.commit()
    return hash

@app.route("/registered")
def finish():
    "finish the auth process"

    token = oauth2.Token(session["request_token"]["oauth_token"],
                         session["request_token"]["oauth_token_secret"])
    token.set_verifier(request.args.get("oauth_verifier"))

    consumer = oauth2.Consumer(CONSUMER_KEY, CONSUMER_SECRET)
    client = oauth2.Client(consumer, token)

    resp, content = client.request("http://www.tumblr.com/oauth/access_token",
                                   "POST")
    if resp["status"] != "200": abort(400)

    d = dict(urlparse.parse_qsl(content))

    token = oauth2.Token(d["oauth_token"], d["oauth_token_secret"])
    client = oauth2.Client(consumer, token)

    resp, data = client.request("http://api.tumblr.com/v2/user/info", "POST")
    user_info_resp = json.loads(data)

    username = user_info_resp["response"]["user"]["name"]

    h = push_user( g.db, g.c, username 
                 , d["oauth_token"]
                 ,d["oauth_token_secret"] )

    return render_template("registered.html", user=username, hash=h)

def render_rss(posts, username):
    items = []
    for item in posts:
        items.append(rss.RSSItem(
            title = u"[{0}] {1}".format(item.get("blog_name", u"unknown"),
                                        item["title"] \
                                            if "title" in item  \
                                                and item["title"] else \
                                        u"Tumblr: {0}".format(item["type"])),
            link = item["post_url"],
            description = post_templates[item["type"]].render(**item),
            pubDate = datetime.datetime.strptime(item["date"],
                                                 "%Y-%m-%d %H:%M:%S GMT"),
            guid = rss.Guid(item["post_url"])
        ))

    feed = rss.RSS2(
        title = u"{0}'s Tumblr Dashboard".format(username),
        link = u"https://{0}.tumblr.com".format(username),
        description = u"Tumblr2RSS generated feed of {0}'s dashboard."\
                      .format(username),
        lastBuildDate = datetime.datetime.utcnow(),
        items = items
    )

    filefeed = cStringIO.StringIO()
    feed.write_xml(filefeed)

    resp = make_response(filefeed.getvalue(), 200)

    filefeed.close()

    resp.headers["Content-Type"] = "application/rss+xml"
    return resp

def page_count(feed_length):
    """The number of pages that will need to be fetched to make of feed
       of the given length"""
    base = feed_length / TUMBLR_POST_LIMIT
    if feed_length % TUMBLR_POST_LIMIT != 0:
        base += 1
    return base

def purge_unauthorized_user(username, key, secret):
    g.c.execute("""
    DELETE from user
    WHERE version = "v1" AND username = ? 
          AND oauth_key = ? AND oauth_secret = ?
    """, (username, key, secret))
    g.db.commit()

def purge_unauthorized_hash(hash, key, secret):
    g.c.execute("""
    DELETE from user
    WHERE version = "v2" AND hash = ? 
      AND oauth_key = ? AND oauth_secret = ?
    """, (username, key, secret))
    g.db.commit()

class TumblrUnauthorizedError(Exception): ""

def get_post_list(key, secret, length):
    consumer = oauth2.Consumer(CONSUMER_KEY, CONSUMER_SECRET)
    token = oauth2.Token(key, secret)
    client = oauth2.Client(consumer, token)

    post_list = []
    for page in xrange(page_count(length)):
        offset = page * TUMBLR_POST_LIMIT
        limit = min(length - offset, TUMBLR_POST_LIMIT)
        url = "http://api.tumblr.com/v2/user/dashboard?offset={0}&limit={1}"\
              .format(offset, limit)
        resp, dash_page = client.request(url, "GET")

        if resp.status == 401:
            raise TumblrUnauthorizedError()

        if resp.status != 200:
            logging.error("{0} {1}".format(resp, dash_page))
            abort(502)

        dash_page = json.loads(dash_page)

        try:
            for post in dash_page["response"]["posts"]:
                post_list.append(post)
        except KeyError:
            logging.error("No posts in response: {0}".format(pformat(dash_page)))
            abort(502)
    return post_list

def request_post_count(request, default=20):
    if "length" not in request.args: return default
    try:
        length = int(request.args["length"])
        if length < 1 or length > FEED_MAX: abort(400)
        return length
    except ValueError: abort(400)

@app.route("/dashboard/<username>.rss")
def user_dash_v1(username):
    g.c.execute("""
                SELECT username, oauth_key, oauth_secret from user
                WHERE version = "v1" and username = ? limit 1
                """, (username,))
    user = g.c.fetchone()
    if user is None: abort(404)
    length = request_post_count(request)
    username, oauth_key, oauth_secret = user
    try:
        posts = get_post_list(oauth_key, oauth_secret, length)
    except TumblrUnauthorizedError:
        purge_unauthorized_user(username, oauth_key, oauth_secret)
        abort(404)
    return render_rss(posts, username=username)

@app.route("/v2/dashboard/<hash>.rss")
def user_dash_v2(hash):
    g.c.execute("""
                SELECT username, oauth_key, oauth_secret from user
                WHERE version = "v2" AND hash = ? limit 1
                """, (hash,))
    user = g.c.fetchone()
    if user is None: abort(404)
    length = request_post_count(request)
    username, oauth_key, oauth_secret = user
    try:
        posts = get_post_list(oauth_key, oauth_secret, length)
    except TumblrUnauthorizedError:
        purge_unauthorized_hash(hash, oauth_key, oauth_secret)
        abort(404)
    return render_rss(posts, username=username)

## Old URL redirects

@app.route("/dashboard")
@app.route("/tumblr/dashboard")
def old_index():
    return redirect(url_for("index"), code=301)

@app.route("/dashboard/register", methods=["GET"])
@app.route("/tumblr/dashboard/register", methods=["GET"])
def old_register():
    return redirect(url_for("register"), code=301)

@app.route("/dashboard/registered")
@app.route("/tumblr/dashboard/registered")
def old_finish():
    return redirect(url_for("finish"), code=301)

@app.route("/tumblr/dashboard/<username>.rss")
def old_user_dash(username):
    return redirect(url_for("user_dash_v1", username=username), code=301)
