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

import config

app = Flask(__name__, template_folder='templates')
app.debug = True

app.secret_key = config.secret_key        # Cookie signing secret
CONSUMER_KEY = config.CONSUMER_KEY        # Tumblr API Consumer Key
CONSUMER_SECRET = config.CONSUMER_SECRET  # Tumblr API Consumer Secret

# Maximum number of posts per posts request to the tumblr API
TUMBLR_POST_LIMIT = 20
# Maximum number of posts allowed in an RSS feed
FEED_MAX = 100

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
    g.db = sqlite3.connect(config.user_db)
    g.c = g.db.cursor()

@app.teardown_request
def teardown(response):
    g.c.close()
    g.db.close()
    return response

@app.route("/")
@app.route("/dashboard")
@app.route("/tumblr/dashboard")
def index():
    return render_template("index.html")

@app.route("/dashboard/register", methods=["GET"])
@app.route("/tumblr/dashboard/register", methods=["GET"])
def register():
    #Else it's a post

    consumer = oauth2.Consumer(CONSUMER_KEY, CONSUMER_SECRET)
    client = oauth2.Client(consumer)

    #According to spec one must be provided, however most
    #implementations could care less
    body = urllib.urlencode({"oauth_callback":
                             url_for("finish", _external=True)})

    resp, content = client.request("http://www.tumblr.com/oauth/request_token",
                                   "POST", body=body)
    if resp["status"] != "200": abort(400)

    session["request_token"] = dict(urlparse.parse_qsl(content))
    return redirect("http://www.tumblr.com/oauth/authorize?oauth_token={0}"\
                    .format(session["request_token"]["oauth_token"]))

@app.route("/dashboard/registered")
@app.route("/tumblr/dashboard/registered")
def finish():
    "finish the auth process"

    token = oauth2.Token(session["request_token"]["oauth_token"],
                         session["request_token"]["oauth_token_secret"])
    token.set_verifier(request.args.get("oauth_verifier"))

    consumer = oauth2.Consumer(CONSUMER_KEY, CONSUMER_SECRET)
    client = oauth2.Client(consumer, token)

    #request the
    resp, content = client.request("http://www.tumblr.com/oauth/access_token",
                                   "POST")
    if resp["status"] != "200": abort(400)

    d= dict(urlparse.parse_qsl(content))

    token = oauth2.Token(d["oauth_token"], d["oauth_token_secret"])
    client = oauth2.Client(consumer, token)

    resp, data = client.request("http://api.tumblr.com/v2/user/info", "POST")
    user_info_resp = json.loads(data)

    g.c.execute("""
                INSERT INTO user values (?, ?, ?)
                """, (user_info_resp["response"]["user"]["name"],
                      d["oauth_token"],
                      d["oauth_token_secret"]))
    g.db.commit()

    return render_template("registered.html",
                           user=user_info_resp["response"]["user"]["name"])

def render_rss(posts, username="Unknown"):
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
        link = u"{0}/{1}".format(url_for("index"), username),
        description = u"Automaticaly generated feed of {0}'s dashboard."\
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
    base = feed_length / TUMBLR_POST_LIMIT
    if feed_length % TUMBLR_POST_LIMIT != 0:
        base += 1
    return base

def get_post_list(client, length):
    post_list = []
    for page in xrange(page_count(length)):
        offset = page * TUMBLR_POST_LIMIT
        limit = min(length - offset, TUMBLR_POST_LIMIT)
        url = "http://api.tumblr.com/v2/user/dashboard?offset={0}&limit={1}"\
              .format(offset, limit)
        resp, dash_page = client.request(url, "GET")

        # Remove unauthorized user's info
        if resp.status == 401:
            g.c.execute("""
            DELETE from user where
                username = ? AND oauth_key = ? AND oauth_secret = ?
            """, (user[0], user[1], user[2]))
            g.db.commit()
            abort(404)

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

@app.route("/dashboard/<username>.rss")
@app.route("/tumblr/dashboard/<username>.rss")
def user_dash(username):
    g.c.execute("""
                SELECT username, oauth_key, oauth_secret from user
                WHERE username = ? limit 1
                """, (username,))

    user = [x for x in g.c]

    if user: user = user[0]
    else: abort(404)

    post_count = 20
    if "length" in request.args:
        try:
            post_count = int(request.args["length"])
            if post_count < 1 or post_count > FEED_MAX: abort(400)
        except ValueError: abort(400)

    consumer = oauth2.Consumer(CONSUMER_KEY, CONSUMER_SECRET)
    token = oauth2.Token(user[1], user[2])
    client = oauth2.Client(consumer, token)

    return render_rss(get_post_list(client, post_count), username=user[0])
