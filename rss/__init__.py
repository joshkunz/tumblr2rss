"""
Various rss scripts to read and modify rss feeds, 
collect other information into rss feeds, or modify rss feed contents.
"""

from flask import Flask, redirect

app = Flask(__name__)
app.debug = True

# You need your own config, for the secret
from rss import config
app.secret_key = config.secret

# import plugins
from rss.tumblr import tumblr
from rss.gawker import gawker

@app.route("/")
def home_page():
	return redirect("http://github.com/Joshkunz/rss-utils")

app.register_blueprint(tumblr, url_prefix="/tumblr")
app.register_blueprint(gawker, url_prefix="/gawker")
