twitter2imap
============
## What does this script?
This python script fetches your Twitter timeline and stores the tweets as
individual emails (rfc822 messages) by using the IMAP(S) protocol.

Storing tweets as emails makes sense because you can read them offline (once
retrieved), keep track (archive your timeline),  search in your timeline with
all of the criteria that are available in your email client, and it helps to
keep your privacy (you do not need to tell Twitter which tweets you want to
forward to a friend or are your favorites, nor which links you click on...).

Hashtags are added to the email subject to allow you to skim your timeline more quickly.

Short links are extended (if possible). This helps keeping your privacy because
all links are extended, and Twitter cannot learn which links you actually
visit. This also helps to improve resiliency by eliminating the need of the URL
shortener resolution service, once the tweet is fetched.

If the destination mailbox does not exist or is empty, the script downloads the 200 most recent tweets of your TL.

If the destination mailbox contains tweets, it tries to download all tweets between now and the most recent tweet that was stored.


## What next?
Future improvements may include:
  * improving code quality
  * Allowing users to post updates (tweets), retweeting and replying by sending an email
  * Store tweets in a hierarchy of subfolders to prevent having thousands of tweets in a single mailbox
  * Add context to a tweet by downloading the answers and parents of a tweet
  * Add more throttling to avoid overloading servers

## How to install and setup?
To use this script, you need to create an "app" on dev.twitter.com

You must then copy the twitter2imap.ini.tmpl file for instance to twitter2imap.ini and fills the blanks

## Some dependancies?
Python 2.7 is required.

This python script makes use of the following (uncommon?) libraries:
python-twitter (version 1.0)
python-imaplib
python-argparse

Use your favorite search engine to get them (and install them with python setup.py {build,install} to get their dependancies as well)
