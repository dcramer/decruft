import os.path
import unittest2

from decruft import Document

fixture_path = os.path.join(os.path.dirname(__file__), 'fixtures')

class DecruftTestCase(unittest2.TestCase):
    def test_disqus_noscript_tag(self):
        content = open(os.path.join(fixture_path, 'disqus.html')).read()
        summary = Document(content).summary().encode('utf-8','ignore')
        self.assertNotIn('<noscript>Please enable JavaScript to view the <a href="http://disqus.com/?ref_noscript=davidcramer">comments powered by Disqus.</a></noscript>', summary)

    def test_comments_powered_by_disqus(self):
        content = open(os.path.join(fixture_path, 'disqus.html')).read()
        summary = Document(content).summary().encode('utf-8','ignore')
        self.assertNotIn('<a href="http://disqus.com" class="dsq-brlink">blog comments powered by <span class="logo-disqus">Disqus</span></a>', summary)
