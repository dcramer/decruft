#!/usr/bin/env python
from BeautifulSoup import NavigableString
from page_parser import parse, get_title, get_body, Unparseable
import logging
import re
from lxml.etree import tostring, tounicode
from lxml.html.clean import Cleaner
import traceback
import sys
logging.basicConfig(level=logging.INFO)
logging.warning('hi')
logging.debug('hi')
REGEXES = { 'unlikelyCandidatesRe': re.compile('share|bookmark|adwrapper|ad_wrapper|combx|comment|disqus|foot|header|menu|meta|nav|rss|shoutbox|sidebar|sponsor',re.I),
    'okMaybeItsACandidateRe': re.compile('and|article|body|column|main',re.I),
    'positiveRe': re.compile('caption|article|body|content|entry|hentry|page|pagination|post|text',re.I),
    'negativeRe': re.compile('adwrapper|ad_wrapper|share|bookmark|nav|combx|comment|contact|foot|footer|footnote|link|media|meta|promo|related|scroll|shoutbox|sponsor|tags|widget',re.I),
    'divToPElementsRe': re.compile('<(a|blockquote|dl|div|img|ol|p|pre|table|ul)',re.I),
    'replaceBrsRe': re.compile('(<br[^>]*>[ \n\r\t]*){2,}',re.I),
    'replaceFontsRe': re.compile('<(\/?)font[^>]*>',re.I),
    'trimRe': re.compile('^\s+|\s+$/'),
    'normalizeRe': re.compile('\s{2,}/'),
    'killBreaksRe': re.compile('(<br\s*\/?>(\s|&nbsp;?)*){1,}/'),
    'videoRe': re.compile('http:\/\/(www\.)?(youtube|vimeo)\.com', re.I),
}

from collections import defaultdict
def describe(node):
    if not hasattr(node, 'tag'):
        return "[text]"
    return "%s#%s.%s" % (
        node.tag, node.get('id', ''), node.get('class',''))


def log_candidates(candidates, print_format=""):
    for candidate, value in candidates.items():
        logging.debug( "%s\t%s\t%s\t%s" %(id(candidate), describe(candidate), value['content_score'], describe(value['elem'])))

#def _text(node):
#    return " ".join(node.findall(text=True))

class Document:
    TEXT_LENGTH_THRESHOLD = 25
    RETRY_LENGTH = 250

    def __init__(self, input, notify=None, **options):
        self.input = input
        self.options = defaultdict(lambda: None)
        for k, v in options.items():
            self.options[k] = v
        self.notify = notify or logging.info
        self.html = None

    def _html(self, force=False):
        if force or self.html is None:
            cleaner = Cleaner(scripts=True, javascript=True, comments=True,
                              style=True, links=True, meta=False, add_nofollow=False,
                              page_structure=False, processing_instructions=True, embedded=False,
                              frames=False, forms=False, annoying_tags=False, remove_tags=None,
                              remove_unknown_tags=False, safe_attrs_only=False)
            self.html = parse(cleaner.clean_html(self.input), self.options['url'], notify=self.notify)
        return self.html
    
    def content(self):
        return get_body(self._html())
    
    def title(self):
        return get_title(self._html())

    def summary(self):
        try:
            ruthless = True
            import pprint
            while True:
                self._html(True)
                [i.drop_tree() for i in self.tags(self.html, 'script', 'style')]

                if ruthless: self.remove_unlikely_candidates()
                self.transform_misused_divs_into_paragraphs()
                candidates = self.score_paragraphs(self.options.get('min_text_length', self.TEXT_LENGTH_THRESHOLD))
                #log_candidates(candidates)
                
                best_candidate = self.select_best_candidate(candidates)
                if best_candidate:
                    article = self.get_article(candidates, best_candidate)
                else:
                    if ruthless:
                        logging.debug("ruthless removal did not work. ")
                        ruthless = False
                        self.debug("ended up stripping too much - going for a safer parse")
                        # try again
                        continue
                    else:
                        logging.debug("Ruthless and lenient parsing did not work. Returning raw html")
                        article = self.html.find('body') or self.html

                cleaned_article = self.sanitize(article, candidates)
                of_acceptable_length = len(cleaned_article or '') >= (self.options['retry_length'] or self.RETRY_LENGTH)
                if ruthless and not of_acceptable_length:
                    ruthless = False
                    continue # try again
                else:
                    return cleaned_article
        except StandardError, e:
            #logging.exception('error getting summary: ' + str(traceback.format_exception(*sys.exc_info())))
            logging.exception('error getting summary: ' )
            raise Unparseable(str(e))

    def get_article(self, candidates, best_candidate):
        # Now that we have the top candidate, look through its siblings for content that might also be related.
        # Things like preambles, content split by ads that we removed, etc.

        sibling_score_threshold = max([10, best_candidate['content_score'] * 0.2])
        output = parse("<div/>")
        for sibling in best_candidate['elem'].getparent().getchildren():
            #if isinstance(sibling, NavigableString): continue#in lxml there no concept of simple text 
            append = False 
            if sibling is best_candidate['elem']:
                append = True
            sibling_key = sibling #HashableElement(sibling)
            if sibling_key in candidates and candidates[sibling_key]['content_score'] >= sibling_score_threshold:
                append = True

            if sibling.tag == "p":
                link_density = self.get_link_density(sibling)
                node_content = sibling.text or ""
                node_length = len(node_content)

                if node_length > 80 and link_density < 0.25:
                    append = True
                elif node_length < 80 and link_density == 0 and re.search('\.( |$)', node_content):
                    append = True

            if append:
                output.append(sibling)
        if output is not None: output.append(best_candidate['elem'])
        return output

    def select_best_candidate(self, candidates):
        sorted_candidates = sorted(candidates.values(), key=lambda x: x['content_score'], reverse=True)
        self.debug("Top 5 candidates:")
        for candidate in sorted_candidates[:5]:
            elem = candidate['elem']
            self.debug("Candidate %s with score %s" % (describe(elem), candidate['content_score']))

        if len(sorted_candidates) == 0:
            return None
        best_candidate = sorted_candidates[0]
        self.debug("Best candidate %s with score %s" % (describe(best_candidate['elem']), best_candidate['content_score']))
        return best_candidate

    def get_link_density(self, elem):
        link_length = len("".join([i.text or "" for i in elem.findall(".//a")]))
        text_length = len(elem.text_content())
        return float(link_length) / max(text_length, 1)

    def score_paragraphs(self, min_text_length):
        candidates = {}
        self.debug(str([describe(node) for node in self.tags(self.html, "div")]))
        elems = self.tags(self.html, "div", "p", "td", 'li', "a")

        for elem in elems:
            parent_node = elem.getparent()
            grand_parent_node = parent_node.getparent()
            elem_key = elem#HashableElement(elem)
            parent_key = parent_node#HashableElement(parent_node)
            grand_parent_key = grand_parent_node#HashableElement(grand_parent_node)

            inner_text = elem.text_content()

            # If this paragraph is less than 25 characters, don't even count it.
            if (not inner_text) or len(inner_text) < min_text_length:
                continue

            if parent_key not in candidates:
                candidates[parent_key] = self.score_node(parent_node)
            if grand_parent_node is not None and grand_parent_key not in candidates:
                candidates[grand_parent_key] = self.score_node(grand_parent_node)

            content_score = 1
            content_score += len(inner_text.split(','))
            content_score += min([(len(inner_text) / 100), 3])
            if elem not in candidates:
                candidates[elem_key] = self.score_node(elem) 
            candidates[elem_key]['content_score'] += content_score
            candidates[parent_key]['content_score'] += content_score
            if grand_parent_node is not None:
                candidates[grand_parent_key]['content_score'] += content_score / 2.0

        # Scale the final candidates score based on link density. Good content should have a
        # relatively small link density (5% or less) and be mostly unaffected by this operation.
        for elem, candidate in candidates.items():
            candidate['content_score'] *= (1 - self.get_link_density(elem))
            self.debug("candidate %s scored %s" % (describe(elem), candidate['content_score']))

        return candidates

    def class_weight(self, e):
        weight = 0
        if e.get('class', None):
            if REGEXES['negativeRe'].search(e.get('class')):
                weight -= 25

            if REGEXES['positiveRe'].search(e.get('class')):
                weight += 25

        if e.get('id', None):
            if REGEXES['negativeRe'].search(e.get('id')):
                weight -= 25

            if REGEXES['positiveRe'].search(e.get('id')):
                weight += 25

        return weight

    def score_node(self, elem):
        content_score = self.class_weight(elem)
        tag = elem.tag.lower()
        if tag == "div":
            content_score += 5
        elif tag == "blockquote":
            content_score += 3
        elif tag == "form":
            content_score -= 3
        elif tag == "th":
            content_score -= 5
        return { 'content_score': content_score, 'elem': elem }

    def debug(self, *a):
        #if self.options['debug']:
            logging.debug(*a)

    def remove_unlikely_candidates(self):

        for elem in self.html.iter():
            s = "%s%s" % (elem.get('class', ''), elem.get('id', ''))
            self.debug(s)
            if REGEXES['unlikelyCandidatesRe'].search(s) and (not REGEXES['okMaybeItsACandidateRe'].search(s)) and elem.tag != 'body':
                self.debug("Removing unlikely candidate - %s" % (s,))
                elem.drop_tree()

    def transform_misused_divs_into_paragraphs(self):
        for elem in self.html.iter():
            if elem.tag.lower() == "div":
                # transform <div>s that do not contain other block elements into <p>s
                if not REGEXES['divToPElementsRe'].search(unicode(''.join(map(tostring, list(elem))))):
                    self.debug("Altering div(#%s.%s) to p" % (elem.get('id', ''), elem.get('class', '')))
                    elem.tag = "p"

    def tags(self, node, *tag_names):
        for tag_name in tag_names:
            for e in node.findall('.//%s' %tag_name):
                yield e

    def sanitize(self, node, candidates):
        for header in self.tags(node, "h1", "h2", "h3", "h4", "h5", "h6"):
            if self.class_weight(header) < 0 or self.get_link_density(header) > 0.33: header.drop_tree()

        for elem in self.tags(node, "form", "iframe"):
            elem.drop_tree()
        allowed = {}
        # Conditionally clean <table>s, <ul>s, and <div>s
        for el in self.tags(node, "table", "ul", "div"):
            if el in allowed:
                continue
            weight = self.class_weight(el)
            el_key = el #HashableElement(el)
            if el_key in candidates:
                content_score = candidates[el_key]['content_score']
            else:
                content_score = 0
            tag = el.tag

            if weight + content_score < 0:
                el.drop_tree()
                self.debug("Conditionally cleaned %s with weight %s and content score %s because score + content score was less than zero." %
                    (describe(el), weight, content_score))
            elif len(el.text_content().split(",")) < 10:
                counts = {}
                for kind in ['p', 'img', 'li', 'a', 'embed', 'input']:
                    counts[kind] = len(el.findall('.//%s' %kind))
                counts["li"] -= 100

                content_length = len(el.text_content()) # Count the text length excluding any surrounding whitespace
                link_density = self.get_link_density(el)
                parent_node = el.getparent()
                if parent_node:
                    if parent_node in candidates:
                        content_score = candidates[parent_node]['content_score']
                    else:
                        content_score = 0
                    pweight = self.class_weight(parent_node) + content_score
                    pname = parent_node.tag
                else:
                    pweight = 0
                    pname = "no parent"
                to_remove = False
                reason = ""

                #if el.tag == 'div' and counts["img"] >= 1:
                #    continue
                if counts["p"] and counts["img"] > counts["p"]:
                    reason = "too many images"
                    to_remove = True
                elif counts["li"] > counts["p"] and tag != "ul" and tag != "ol":
                    reason = "more <li>s than <p>s"
                    to_remove = True
                elif counts["input"] > (counts["p"] / 3):
                    reason = "less than 3x <p>s than <input>s"
                    to_remove = True
                elif content_length < (self.options.get('min_text_length', self.TEXT_LENGTH_THRESHOLD)) and (counts["img"] == 0 or counts["img"] > 2):
                    reason = "too short a content length without a single image"
                    to_remove = True
                elif weight < 25 and link_density > 0.5 and content_length < (2*self.TEXT_LENGTH_THRESHOLD):
                        reason = "too many links for its weight less than 25 (#{weight})"
                        to_remove = True
                elif weight >= 25 and link_density > 0.5:
                    reason = "too many links for its weight (#{weight})"
                    to_remove = True
                elif (counts["embed"] == 1 and content_length < 75) or counts["embed"] > 1:
                    reason = "<embed>s with too short a content length, or too many <embed>s"
                    to_remove = True
                if el.tag == 'div' and counts['img'] >= 1 and to_remove:
                    imgs = el.findall('.//img')
                    valid_img = False
                    self.debug(tounicode(el))
                    for img in imgs:

                        height = img.get('height')
                        width = img.get('width')
                        self.debug ("height %s width %s" %(repr(height), repr(width)))
                        if (height and int(height) >= 50) or (width and int(width) >= 50):
                            valid_img = True
                            self.debug("valid image" + tounicode(img))
                            break
                    if valid_img:
                        to_remove = False
                        self.debug("Allowing %s" %el.text_content())
                        for desnode in self.tags(el, "table", "ul", "div"):
                            allowed[desnode] = True
                    #find x non empty preceeding and succeeding siblings
                    """
                        i, j = 0, 0
                        x  = 1
                        siblings = []
                        for sib in el.itersiblings():
                            self.debug(sib.text_content())
                            sib_content_length = len(sib.text_content())
                            if sib_content_length:
                                i =+ 1
                                siblings.append(sib_content_length)
                                if i == x:
                                    break
                        for sib in el.itersiblings(preceding=True):
                            self.debug(sib.text_content())
                            sib_content_length = len(sib.text_content())
                            if sib_content_length:
                                j =+ 1
                                siblings.append(sib_content_length)
                                if j == x:
                                    break
                        self.debug(str(siblings))
                        if siblings and sum(siblings) > 1000 :
                            to_remove = False
                            self.debug("Allowing %s" %el.text_content())
                            for desnode in self.tags(el, "table", "ul", "div"):
                                allowed[desnode] = True
                    """
                if to_remove:
                    self.debug("Conditionally cleaned %s#%s.%s with weight %s and content score %s because it has %s." %
                        (el.tag, el.get('id',''), el.get('class', ''), weight, content_score, reason))
                    self.debug("pname %s pweight %s" %(pname, pweight))
                    el.drop_tree()

        for el in ([node] + [n for n in node.iter()]):
            if not (self.options['attributes']):
                #el.attrib = {} #FIXME:Checkout the effects of disabling this
                pass

        return tounicode(node)

class HashableElement():
    def __init__(self, node):
        self.node = node
        self._path = None

    def _get_path(self):
        if self._path is None:
            reverse_path = []
            node = self.node
            while node is not None:
                node_id = (node.tag, tuple(node.attrib.items()), node.text)
                reverse_path.append(node_id)
                node = node.getparent()
            self._path = tuple(reverse_path)
        return self._path
    path = property(_get_path)

    def __hash__(self):
        return hash(self.path)

    def __eq__(self, other):
        return self.path == other.path

    def __getattr__(self, tag):
        return getattr(self.node, tag)

def main():
    import sys
    from optparse import OptionParser
    parser = OptionParser(usage="%prog: [options] [file]")
    parser.add_option('-v', '--verbose', action='store_true')
    parser.add_option('-u', '--url', help="use URL instead of a local file")
    (options, args) = parser.parse_args()
    
    if not (len(args) == 1 or options.url):
        parser.print_help()
        sys.exit(1)
    logging.basicConfig(level=logging.INFO)

    file = None
    if options.url:
        import urllib
        file = urllib.urlopen(options.url)
    else:
        file = open(args[0])
    try:
        print Document(file.read(), debug=options.verbose).summary().encode('ascii','ignore')
    finally:
        file.close()

if __name__ == '__main__':
    main()
