from pprint import pformat
import base64
import datetime
import io
import logging
import os
import sqlite3

from authlib.flask.client import OAuth
from flask import Flask, request, g, session, abort, \
                  redirect, make_response, url_for
from flask.templating import render_template
from jinja2 import Template
from gunicorn.app import base as gunicorn_base
import PyRSS2Gen as rss
import yaml

# Maximum number of posts per posts request to the tumblr API
TUMBLR_POST_LIMIT = 20

# Add 256 bits of randomness + 1 to make base64 work better
KEY_BYTES = (256 // 8) + 1

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
for name, values in post_templates.items():
    post_templates[name] = Template(post_templates[name])

class SessionOAuthCache(object):

    KEY = "oauth_request_cache"

    @classmethod
    def save(cls, token):
        session[cls.KEY] = token

    @classmethod
    def fetch(cls):
        v = session[cls.KEY]
        return v

def global_fetch_token(req):
    del req # Unused
    return g.fetch_token()

app = Flask(__name__, template_folder='templates')
oauth = OAuth(app, fetch_token=global_fetch_token)

@app.before_request
def setup():
    g.db = sqlite3.connect(app.config["USER_DB_PATH"])
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
    finish_uri = url_for("finish", _external=True)
    return oauth.tumblr.authorize_redirect(finish_uri)

def gen_hash():
    "Generate a one-time unique hash for the given user"
    key = os.urandom(KEY_BYTES)
    return base64.urlsafe_b64encode(key).decode()

def remove_user(conn, curs, username):
    "Remove all entries pertaining to a user from the database"
    curs.execute("""DELETE FROM user where username = ?""", (username,))
    conn.commit()

def push_user(conn, curs, username, token):
    remove_user(conn, curs, username)
    hash = gen_hash()
    curs.execute("""
        INSERT INTO user (version,hash,username,oauth_key,oauth_secret)
        VALUES (?,?,?,?,?)""",
        ("v2", hash, username, token["oauth_token"], token["oauth_token_secret"]))
    conn.commit()
    return hash

@app.route("/registered")
def finish():
    "finish the auth process"

    token = oauth.tumblr.authorize_access_token()
    result = oauth.tumblr.post("user/info", token=token)
    if result.status_code != 200:
        abort(502)
    user_info_resp = result.json()
    username = user_info_resp["response"]["user"]["name"]

    h = push_user(g.db, g.c, username, token)
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

    filefeed = io.BytesIO()
    feed.write_xml(filefeed)

    resp = make_response(filefeed.getvalue(), 200)

    filefeed.close()

    resp.headers["Content-Type"] = "application/rss+xml"
    return resp

def page_count(feed_length):
    """The number of pages that will need to be fetched to make of feed
       of the given length"""
    base = feed_length // TUMBLR_POST_LIMIT
    if feed_length % TUMBLR_POST_LIMIT != 0:
        base += 1
    return base

def purge_unauthorized_user(username):
    token = oauth.tumblr.token
    g.c.execute("""
    DELETE from user
    WHERE version = "v1" AND username = ?
          AND oauth_key = ? AND oauth_secret = ?
    """, (username, token["oauth_token"], token["oauth_token_secret"]))
    g.db.commit()

def purge_unauthorized_hash(hash):
    token = oauth.tumblr.token
    g.c.execute("""
    DELETE from user
    WHERE version = "v2" AND hash = ?
      AND oauth_key = ? AND oauth_secret = ?
    """, (hash, token["oauth_token"], token["oauth_token_secret"]))
    g.db.commit()

class TumblrUnauthorizedError(Exception): ""

def get_post_list(length):
    post_list = []
    for page in range(page_count(length)):
        offset = page * TUMBLR_POST_LIMIT
        limit = min(length - offset, TUMBLR_POST_LIMIT)
        resp = oauth.tumblr.get("user/dashboard", params={
            "offset": offset,
            "limit": limit,
        })

        if resp.status_code == 401:
            raise TumblrUnauthorizedError()

        if resp.status_code != 200:
            logging.error("%s", resp)
            abort(502)

        dash_page = resp.json()

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
        if length < 1 or length > app.config["FEED_MAX"]: abort(400)
        return length
    except ValueError: abort(400)

@app.route("/dashboard/<username>.rss")
def user_dash_v1(username):
    def _fetch_token_v1():
        g.c.execute("""
                    SELECT oauth_key, oauth_secret from user
                    WHERE version = "v1" and username = ? limit 1
                    """, (username,))
        user = g.c.fetchone()
        if user is None: abort(404)
        token, secret = user
        return dict(oauth_token=token, oauth_token_secret=secret)
    g.fetch_token = _fetch_token_v1
    length = request_post_count(request)
    try:
        posts = get_post_list(length)
    except TumblrUnauthorizedError:
        purge_unauthorized_user(username)
        abort(404)
    return render_rss(posts, username=username)

@app.route("/v2/dashboard/<hash>.rss")
def user_dash_v2(hash):
    username = None
    def _fetch_token_v2():
        nonlocal username
        g.c.execute("""
                    SELECT username, oauth_key, oauth_secret from user
                    WHERE version = "v2" AND hash = ? limit 1
                    """, (hash,))
        user = g.c.fetchone()
        if user is None: abort(404)
        username, token, secret = user
        return dict(oauth_token=token, oauth_token_secret=secret)
    g.fetch_token = _fetch_token_v2
    length = request_post_count(request)
    try:
        posts = get_post_list(length)
    except TumblrUnauthorizedError:
        purge_unauthorized_hash(hash)
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

def load_app_config(app, cfg):
    app_config = {
        "FEED_MAX": cfg["feed_max"],
        "USER_DB_PATH": cfg["user_db_path"],
    }
    if "server_name" in cfg:
        app_config["SERVER_NAME"] = cfg["server_name"]
    app.config.from_mapping(app_config)
    app.secret_key = cfg["secret_key"]

def load_oauth_config(oauth, cfg):
    oauth.register(
        name="tumblr",
        client_id=cfg["consumer_key"],
        client_secret=cfg["consumer_secret"],
        request_token_url="https://www.tumblr.com/oauth/request_token",
        access_token_url="https://www.tumblr.com/oauth/access_token",
        authorize_url="http://www.tumblr.com/oauth/authorize",
        api_base_url="https://api.tumblr.com/v2/",
        save_request_token=SessionOAuthCache.save,
        fetch_request_token=SessionOAuthCache.fetch,
    )

class Server(gunicorn_base.BaseApplication):

    def __init__(self, app, options=None):
        self.options = options or {}
        self.application = app
        super(Server, self).__init__()

    def load_config(self):
        config = dict([(key, value) for key, value in self.options.items()
                       if key in self.cfg.settings and value is not None])
        for key, value in config.items():
            self.cfg.set(key.lower(), value)

    def load(self):
        return self.application


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--config", type=str, required=True)
    parser.add_argument("--host", type=str, default="127.0.0.1")
    parser.add_argument("--port", type=str, default="8080")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    if args.debug:
        app.debug = True
    with open(args.config, 'r') as cfg_file:
        cfg = yaml.load(cfg_file)
    load_app_config(app, cfg)
    load_oauth_config(oauth, cfg)

    server = Server(app, options={
        "bind": "{host}:{port}".format(host=args.host, port=args.port),
        "workers": args.workers,
        "errorlog": "-",
        "capture_output": True,
    })
    server.run()
