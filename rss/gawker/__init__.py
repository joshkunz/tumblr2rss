from flask import Blueprint, make_response
import requests
from lxml import etree
import json

######### Config ##########

GAWKER_API = "http://api.gawker.com/sponge/api/v1"
FEED_URL = "http://feeds.gawker.com/{0}/full"

###########################

gawker = Blueprint("gawker", __name__)

def gen_url(data):
	"""Turn a data map into url parameters"""
	data = map(lambda x: "=".join(x), data)
	data = "&".join(data)
	return data

def get_views(*urls):
	"""Get the view counts for a gawker blog post"""
	data = [("url", url) for url in urls] + [("source", "views")]
	resp = requests.get("{0}/getStats?{1}".format(GAWKER_API, gen_url(data)))
	parsed = json.loads(resp.text)
	return parsed["data"]

@gawker.route("/top3/<site>")
@gawker.route("/top3/<site>.rss")
def top3(site):
	feed_page = requests.get(FEED_URL.format(site))
	feed = etree.XML(feed_page.text.encode('utf-8'))

	urls = feed.xpath("//feedburner:origLink/text()", namespaces=feed.nsmap)
	sd = sorted(get_views(*urls).items(), 
				key=lambda x: x[1]["views"].get("totalViews"),
				reverse=True)
	top3 = dict(sd[:3])
	channel = feed.xpath("/rss/channel")[0]
	for e in channel.xpath("item", namespaces=feed.nsmap):
		link = e.xpath("feedburner:origLink/text()", namespaces=feed.nsmap)[0]
		if link not in top3:
			channel.remove(e)
	
	resp = make_response(etree.tostring(feed), 200)
	resp.headers["Content-Type"] = "application/rss+xml"
	return resp

