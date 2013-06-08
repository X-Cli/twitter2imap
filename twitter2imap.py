#!/opt/local/bin/python2.7

import sys
import os
import twitter
import imaplib
import re
import time
import hashlib
import hmac
import httplib
import HTMLParser
import argparse
import ConfigParser

################################################################################
#TODO Cannot currently handle links in the form protocol://domainname:port/somepath
def resolv_a_short_link(link):
    MAX_REDIR = 10
    redir_cnt = 0
    found_a_link = True

    while found_a_link and redir_cnt < MAX_REDIR:
        found_a_link = False
        if link[0:5] == "https":
            protocol = "https://"
            port = 443
        else:
            protocol = "http://"
            port = 80

        domain = link[len(protocol):]
        domain = domain[:domain.find("/")]
        path=link[len(protocol) + len(domain):]

        try:
            if protocol == "http://":
                conn = httplib.HTTPConnection(domain, port)
            else:
                conn = httplib.HTTPSConnection(domain, port)
                
            conn.request("HEAD", path)
            resp = conn.getresponse()
            for header in resp.getheaders():
                if header[0] == "location":
                    link = header[1]
                    if link[0] == "/": #relative link
                        link = protocol + domain + link
                    found_a_link = True
                    redir_cnt += 1
                    conn.close()
                    break
            conn.close()
        except:
            #Something went wrong with this link ; return as is
            conn.close()
            return link

    return link
################################################################################
def getMsgCountInMailBox(imapapi, twitter_mailbox):
    (select_ok, _) = imapapi.select(twitter_mailbox)
    if select_ok == 'NO':
        imapapi.create(twitter_mailbox)
        select_ok = imapapi.select(twitter_mailbox)
        updates_cnt = 0
    else:
        (status_ok, status_answer) = imapapi.status(twitter_mailbox, "(messages)")
        if status_ok != "OK":
            print "Unable to get number of messages in Twitter mailbox: " + status_answer
            return -1
        
        re_result = re.match(r".*\(MESSAGES (\d+)\).*", status_answer[0])
        if not re_result:
            print "Unable to get number of messages: invalid format"
            return -1
        
        updates_cnt = int(re_result.group(1))
    return updates_cnt
################################################################################
def getLastTwitterID(imapapi, twitter_mailbox):
    TwitterID_header = "TwitterID: "

    updates_cnt = getMsgCountInMailBox(imapapi, twitter_mailbox)
    if updates_cnt == -1:
        return -1 

    #if twitter updates are already stored, get the highest ID in these messages
    if updates_cnt != 0:
        twitter_since_id=0

        #Fetches the last 100 messages stored on the IMAP server (because for
        # some reasons, the most "recent" email is not necessarily the most
        # "recent" in Twitter)
        (fetch_ok, fetch_list) = imapapi.fetch(
                str(max((updates_cnt - 100), 1)) + ":" + str(updates_cnt), 
                "(rfc822.header)"
                ) 

        if fetch_ok != 'OK':
            print "Unable to fetch last message: " + fetch_list
            return -1
            
        i=0
        fetch_list_len =  len(fetch_list)
        while i < fetch_list_len:
            rfc822_msg_headers = fetch_list[i][1].split("\n")

            twitter_since_id_temp=0
            for header in rfc822_msg_headers:
                if header[0:len(TwitterID_header)] == TwitterID_header:
                    twitter_since_id_temp = header[len(TwitterID_header):]
                

            if twitter_since_id_temp > twitter_since_id:
                twitter_since_id = twitter_since_id_temp 

            # +2 because there is a useless ")" every two elements in the list
            i += 2

        if twitter_since_id == 0:
            print "Unable to find the Twitter ID in the last messages; " + \
                "martian msg in Twitter mailbox"
            return -1    
    else:
        twitter_since_id = 0
    
    return twitter_since_id

################################################################################
def fetchTweets(twiapi, twitter_since_id, max_fetched_tweets):
    if max_fetched_tweets == 0:
        countLimit = 200
    else:
        countLimit = max(1, min(max_fetched_tweets, 200))

    dict_tweets = {}

    if twitter_since_id == 0:
        tweets = twiapi.GetHomeTimeline(count=countLimit, include_entities=True)
        for tweet in tweets:
            dict_tweets[tweet.GetId()]=tweet
    else:
        smallest_id = 0

        some_tweets = twiapi.GetHomeTimeline(count=countLimit, 
                                             since_id=twitter_since_id, 
                                             include_entities=True)
        for tweet in some_tweets:
            try:
                tweet_id = int(tweet.GetId())
                if smallest_id == 0 or smallest_id > tweet_id:
                    smallest_id = tweet_id
                dict_tweets[tweet_id]=tweet
            except:
                #Invalid ID (not a number)
                print "ID not a number! Got: " + tweet_id
        
        while len(some_tweets) > 1:
            #Some throttling to avoid hassling twitter's servers
            time.sleep(5)
  
            some_tweets = twiapi.GetHomeTimeline(count=countLimit, 
                                                 since_id=twitter_since_id, 
                                                 max_id=smallest_id, 
                                                 include_entities=True)

            for tweet in some_tweets:
                try:
                    tweet_id = int(tweet.GetId())
                    if not dict_tweets.has_key(tweet_id):
                        if smallest_id > tweet_id:
                            smallest_id = tweet_id
                        dict_tweets[tweet_id]=tweet
                except ValueError:
                    #Invalid ID (not a number)
                    print "ID not a number! Got: " + tweet_id

    return dict_tweets
################################################################################
def shutdown(imapapi, exitval):
    imapapi.logout()
    sys.exit(exitval)
################################################################################
def getListHashTag(tweet):        
    hts = []
    for ht in tweet.hashtags:
        hts.append(ht.text)

    return hts

################################################################################
def generate_links_text(indexed_links):
    #List as footnote the extended links
    if len(indexed_links) > 0:
        links_text=""
        i = 1
        for item in indexed_links:
            links_text += "[Link " + str(i) + "] " + item + "\n"
            i += 1
    else:
        links_text=""

    return links_text
################################################################################
def generate_email_elmts(tweet):
    #If the tweet is a retweet, format differently the text "someone said:\n
    # tweet content" and change email subject to "Retweet from"
    original_tweet = tweet.GetRetweeted_status()        
    if original_tweet:
        retweeter = tweet.GetUser()
        author = original_tweet.GetUser()
        author_screenname = author.GetScreenName()
        author_name = author.GetName()

        subject = "Retweet from @" + retweeter.GetScreenName()
        email_text = author_name + " (@" + author_screenname + \
             ") said:\n" + original_tweet.GetText()

        tweet = original_tweet
    else:
        author = tweet.GetUser()
        author_screenname = author.GetScreenName()
        author_name = author.GetName()

        subject = "Tweet from @" + author_screenname
        email_text = tweet.GetText()

    return (author, subject, email_text, tweet)
################################################################################
def extract_hashtags(tweet):
    hashtag_list = getListHashTag(tweet)        
    subject_suffix = ""
    if len(hashtag_list) > 0:
        subject_suffix = " --"
        for hashtag in hashtag_list:
            subject_suffix += " #" + hashtag
    return subject_suffix
################################################################################
def preventHeaderInjection(some_text):
    return some_text.replace("\n", "").replace("\r", "")
################################################################################
def saveTweetsToImap(imapapi, twitter_mailbox, new_tweets, myEmailAddress, replyBot, secret):
    #Instanciate an HTML parser to unescape the tweet text (since we generate a text/plain, this should be safe
    h = HTMLParser.HTMLParser()

    for tweet_key in new_tweets:
        tweet = new_tweets[tweet_key]
 
        tweet_id=str(tweet.GetId())

        (author, subject, email_text, tweet) = generate_email_elmts(tweet)
        author_name = preventHeaderInjection(author.GetName())
        author_screenname = author.GetScreenName()

        #Extract hashtags
        subject += extract_hashtags(tweet)

        #Extends short links
        (email_text, links_text) = resolv_short_links(email_text, tweet)

        #Build security token for retweets and replies
        securityTokenConstructor = hmac.new(secret);
        securityTokenConstructor.update(tweet_id)
        securityToken = securityTokenConstructor.hexdigest()

        email = "From: " + author_name + " <" + replyBot + ">\n" + \
                "To: <" + myEmailAddress + ">\n" + \
                "Date: " + time.strftime("%a, %d %b %Y %H:%M:%S +0000", 
                           time.gmtime(tweet.GetCreatedAtInSeconds())) + "\n" + \
                "Subject: " + preventHeaderInjection(subject) + "\n" + \
                "Content-Type: text/plain\n" + \
                "Content-Encoding: utf-8\n" + \
                "TwitterID: " + preventHeaderInjection(tweet_id) + "\n" + \
                "\n" + \
                h.unescape(email_text) + "\n" + \
                "\n\n\n\n\n\n\n" + \
                links_text + \
                "---------------------------------------------------\n" + \
                "ID=" + tweet_id + "\n" + \
                "SecurityToken=" + securityToken + "\n" + \
                "Twitter link= https://twitter.com/" + author_screenname + \
                    "/status/" + tweet_id + "\n"

        #Send IMAP cmd to store the tweet
        imapapi.append(twitter_mailbox, "(New)", tweet.GetCreatedAtInSeconds(),
            email.encode('utf-8', 'replace'))

################################################################################
def resolv_short_links(email_text, tweet):
    lnk_cnt = 1
    links_text = ""

    for url in tweet.urls:
        email_text = email_text.replace(url.url, "[Link " + str(lnk_cnt) + "]")
        links_text += "[Link " + str(lnk_cnt) + "]= " + \
            resolv_a_short_link(url.expanded_url) + "\n"

    return email_text, links_text
################################################################################

if __name__ == "__main__":
    try:
        parser = argparse.ArgumentParser ()
        parser.add_argument('-c', help='Config file (e.g. twitter2imap.ini)', dest='config_file', 
            default="twitter2imap.ini") 

        if sys.argv[1] == "-h" or sys.argv[1] == "--help":
            parser.print_help()
            sys.exit(0)
        
        args = parser.parse_args()

        config = ConfigParser.ConfigParser()
        config.readfp(open(args.config_file, "r"))
    except IOError as e:
        print e
        sys.exit(1)

    try:
        try:
            consumer_key = config.get("Twitter", "Consumer Key")
            consumer_secret = config.get("Twitter", "Consumer Secret")
            access_token_key = config.get("Twitter", "Access Token Key")
            access_token_secret = config.get("Twitter", "Access Token Secret")
        except ConfigParser.NoSectionError:
            print "Missing Twitter section in config file. This is a problem."
            sys.exit(1)
        except ConfigParser.NoOptionError:
            print "Missing Twitter options in config file. This is a problem."
            sys.exit(1)

        try:
            try:
                default_use_tls = True
                use_tls = config.get("IMAP", "Use TLS").lower()
                if use_tls == "":
                    use_tls = default_use_tls
                elif use_tls[0:1] == "t" or use_tls[0:1] == "y":
                    use_tls = True
                else:
                    use_tls = False
            except ConfigParser.NoOptionError:
                use_tls = default_use_tls
                print  "Warning: the IMAP section does not have a Use TLS option. " + \
                    "Defaulting to Use TLS=" + str(default_use_tls)

            try:
                default_imap_host = "127.0.0.1"
                imap_host = config.get("IMAP", "Host")
                if imap_host=="":
                    imap_host = default_imap_host
            except ConfigParser.NoOptionError:
                imap_host = default_imap_host
                print "Warning: the IMAP section does not have a Host option. " + \
                    "Defaulting to "+ default_imap_host

            try:
                imap_port = config.get("IMAP", "Port")
                imap_port=int(imap_port)

            except ValueError:
                print "Error: the IMAP port number is invalid."
                sys.exit(1)
            except ConfigParser.NoOptionError:
                if use_tls:
                    imap_port = 993
                else:
                    imap_port = 143
                
            try:
                imap_login = config.get("IMAP", "Login")
                imap_pwd = config.get("IMAP", "Password")
            except ConfigParser.NoOptionError:
                print "Error: No Login/Password found in config file."
                sys.exit(1)
        except ConfigParser.NoSectionError:
            print "No section IMAP in config file. This is a problem."
            sys.exit(1)


        try:
            twitter_mailbox = config.get("Twitter2IMAP", "Mailbox")
            if twitter_mailbox == "":
                twitter_mailbox = "Twitter"

            max_fetched_tweets = config.get("Twitter2IMAP", "Max Fetched")
            if max_fetched_tweets=="":
                max_fetched_tweets = 200
            else:
                try:
                    max_fetched_tweets = int(max_fetched_tweets)
                except ValueError:
                    max_fetched_tweets = 200
                    print "Error: Max Fetch value is invalid. Defaulting to " + \
                        str(max_fetched_tweets)

            try:
                reply_bot_address = config.get("Twitter2IMAP", "Bot Email Address")
            except ConfigParser.NoOptionError:
                reply_bot_address = ""

            try:
                myEmailAddress = config.get("Twitter2IMAP", "My Email Address")
            except ConfigParser.NoOptionError:
                myEmailAddress = ""

        except ConfigParser.NoSectionError:
            print "Missing Twitter2IMAP section in config file."
            sys.exit(1)

    except Exception as e:
        print "Unable to parse arguments or config file"
        print e
        sys.exit(1)


    twiapi = twitter.Api( consumer_key=consumer_key,
                          consumer_secret=consumer_secret,
                          access_token_key=access_token_key,
                          access_token_secret=access_token_secret
                          )

    if use_tls :
        imapapi = imaplib.IMAP4_SSL(host=imap_host, port=imap_port)
    else:
        imapapi = imaplib.IMAP4(host=imap_host, port=imap_port)
      
    if(not imapapi):
        print "Unable to open connection to IMAP server"
        shutdown(imapapi, 1)

    # Login to IMAP server
    (login_ok, login_msg) = imapapi.login(imap_login, imap_pwd)
    if login_ok != 'OK':
        print "Unable to login to IMAP server: " + login_msg
        shutdown(imapapi, 1)

    # What is the ID of the last fetched update ?
    twitter_since_id = getLastTwitterID(imapapi, twitter_mailbox)

    if twitter_since_id == -1:
        shutdown(imapapi, 1)

    #Fetches Twitter Timeline
    new_tweets = fetchTweets(twiapi, twitter_since_id, max_fetched_tweets)

    if len(new_tweets) == 0:
        shutdown(imapapi, 1)

    #Save tweets to IMAP
    saveTweetsToImap(imapapi, twitter_mailbox, new_tweets,
        myEmailAddress, reply_bot_address, 
        hashlib.sha256(consumer_key + consumer_secret).hexdigest())

    shutdown(imapapi, 0)

