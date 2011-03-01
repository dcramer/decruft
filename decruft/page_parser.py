import re
from url_helpers import absolute_url
from BeautifulSoup import BeautifulSoup, HTMLParseError, UnicodeDammit
from logging import error
import lxml.html as html
from lxml.etree import tostring

__all__ = [
    'Unparseable',
    'parse',
    'get_title',
    'get_body',
    'ascii']

def debug(s): pass

class Unparseable(ValueError):
    pass

def parse(raw_content, base_href=None, notify=lambda x: None):
    try:
        content = UnicodeDammit(raw_content, isHTML=True).markup
        cleaned = _remove_crufty_html(content)
        debug("Cleaned content: %s" % (cleaned,))
        return create_doc(cleaned, base_href)
    except HTMLParseError, e:
        notify("parsing (%s) failed: %s" % (parse_method.__name__, e))
    raise Unparseable()

def get_title(doc):
    title = unicode(getattr(doc.find('.//title'), 'text', ''))
    if not title:
        return None
    return normalize_spaces(title)


def get_body(doc):
    [ elem.drop_tree() for elem in doc.xpath('.//script | .//link | .//style') ]
    raw_html = unicode(tostring(doc.body or doc))
    cleaned = clean_attributes(raw_html)
    try:
        #BeautifulSoup(cleaned) #FIXME do we really need to try loading it?
        return cleaned
    except HTMLParseError: #FIXME find the equivalent lxml error
        error("cleansing broke html content: %s\n---------\n%s" % (raw_html,cleaned))
        return raw_html

def ascii(s):
    return s.decode('ascii', 'ignore')

class Replacement(object):
    def __init__(self, desc, regex, replacement):
        self.desc = desc
        self.regex = regex
        self.replacement = replacement
    
    def apply(self, content):
#        # useful for debugging:
#        try:
#            print self. desc + ':' + str(self.regex.findall(content))
#        except RuntimeError: pass
        return self.regex.sub(self.replacement, content)

def create_doc(content, base_href):
    html_doc = html.fromstring(content)
    if base_href:
        html_doc.make_links_absolute(base_href, resolve_base_href=True)
    else:
        html_doc.resolve_base_href()
    return html_doc


# a bunch of regexes to hack around lousy html
dodgy_regexes = (
    Replacement('javascript',
        regex=re.compile('<script.*?</script[^>]*>', re.DOTALL | re.IGNORECASE),
        replacement=''),

    Replacement('double double-quoted attributes',
        regex=re.compile('(="[^"]+")"+'),
        replacement='\\1'),

    Replacement('unclosed tags',
        regex = re.compile('(<[a-zA-Z]+[^>]*)(<[a-zA-Z]+[^<>]*>)'),
        replacement='\\1>\\2'),

    Replacement('unclosed (numerical) attribute values',
        regex = re.compile('(<[^>]*[a-zA-Z]+\s*=\s*"[0-9]+)( [a-zA-Z]+="\w+"|/?>)'),
        replacement='\\1"\\2'),
    )
    

# helpers for parsing
def normalize_spaces(s):
    """replace any sequence of whitespace
    characters with a single space"""
    return ' '.join(s.split())

def _remove_crufty_html(content):
    for replacement in dodgy_regexes:
        content = replacement.apply(content)
    return content

def _parse_methods():
    def unicode_cleansed(content, base_href):
        content = UnicodeDammit(content, isHTML=True).markup
        cleaned = _remove_crufty_html(content)
        debug("Cleaned content: %s" % (cleaned,))
        return beautiful_soup(cleaned, base_href)

    def ascii_cleansed(content, base_href):
        content = ascii(content)
        cleaned = _remove_crufty_html(content)
        debug("Cleaned content: %s" % (cleaned,))
        return beautiful_soup(cleaned, base_href)

    return (
        beautiful_soup,
        unicode_cleansed,
        ascii_cleansed)

# strip out a set of nuisance html attributes that can mess up rendering in RSS feeds
bad_attrs = ['width','height','style','[-a-z]*color','background[-a-z]*']
single_quoted = "'[^']+'"
double_quoted = '"[^"]+"'
non_space = '[^ "\'>]+'
htmlstrip = re.compile("<" # open
    "([^>]+) " # prefix
    "(?:%s) *" % ('|'.join(bad_attrs),) + # undesirable attributes
    '= *(?:%s|%s|%s)' % (non_space, single_quoted, double_quoted) + # value
    "([^>]*)"  # postfix
    ">"        # end
, re.I)
def clean_attributes(html):
    while htmlstrip.search(html):
        html = htmlstrip.sub('<\\1\\2>', html)
    return html

