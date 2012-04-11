"""
Various rss scripts to read and modify rss feeds, 
collect other information into rss feeds, or modify rss feed contents.
"""

from flask import Flask

app = Flask(__name__)
app.debug = True
from rss import config
app.secret_key = config.secret

# import plugins
from rss.tumblr import tumblr

app.register_blueprint(tumblr, url_prefix="/tumblr")
