twitter2imap
============
## What does this script?
This python script fetches your Twitter timeline and stores the tweets as
individual emails (rfc822 messages) by using the IMAP(S) protocol.

Storing tweets as emails makes sense because you can read them offline (once
retrieved), search in your timeline with all of the criteria that are available
in your email client, and it helps to keep your privacy (you do not need to tell
Twitter which tweets you want to forward to a friend or are your favorites, nor
which links you click on...).

Hashtags are extracted and added to the email subject.

Short links are extended (if possible). This helps keeping your privacy because
all links are extended, and Twitter cannot learn which links you actually
visit. This also helps to improve resiliency by eliminating the need of the URL
shortener resolution service, once the tweet is fetched.

If the destination mailbox does not exist or is empty, the script downloads the 100 most recent tweets of your TL.

If the destination mailbox contains tweets, it tries to download all tweets between now and the most recent tweet that was stored.

## What next?
Future improvements may include:
  * improving code quality
  * Allowing users to post updates (tweets), retweeting and replying by sending an email
  * Store tweets in a hierarchy of subfolders to prevent having thousands of tweets in a single mailbox
  * Add context to a tweet by downloading the answers and parents of a tweet
  * Add more throttling to avoid overloading servers
  * Add an option to prevent the script from downloading everything you missed if you do not want to
  * Find a way to get full text of long tweets since some are truncated for some strange reason (might be the API)


## How to install and setup?
To use this script, you need to create an "app" on dev.twitter.com and fills the following variables before lauching it

consumer_key="some value"
consumer_secret="some other value"
access_token_key="some other value2"
access_token_secret="some other value3"

use_ssl = True #Or not
imap_host = "SomeIPAddressOrDomainName"
imap_port = 993
imap_login="Me"
imap_pwd="MyPasswd"

replyBot = "SomeEmailAddress; Unused for now"
myEmailAddress = "Your Email Address"
twitter_mailbox = "Twitter"

## Some dependancies?

This python script makes use of the following (uncommon?) libraries:
python-twitter (which makes use of python-oauth2)
python-imaplib

Use your favorite search engine to get them.

