#!/usr/bin/python

import sys
import twitter
import imaplib
import re
import time
import hashlib
import hmac
import httplib
import HTMLParser

consumer_key=""
consumer_secret=""
access_token_key=""
access_token_secret=""

use_ssl = True
imap_host = "SomeIPAddressOrDomainName"
#Does not work yet with starttls : either cleartext connection :( or implicit TLS (IMAPS)
imap_port = 993
imap_login="Me"
imap_pwd="MyPasswd"

replyBot = "SomeEmailAddressThatWillRunSomeScriptSomeDayToUnderstandAnswers"
myEmailAddress = "Your Email Address"
twitter_mailbox = "Twitter"

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
        (fetch_ok, fetch_list) = imapapi.fetch(str(max((updates_cnt - 100), 1)) + ":" + str(updates_cnt), "(rfc822.header)") 
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
            # +2 because there is a useless ")" every two elements in the list (for some reason...)
            i += 2

        if twitter_since_id == 0:
            print "Unable to find the Twitter ID in the last messages; martian msg in Twitter mailbox"
            return -1    
    else:
        twitter_since_id = 0
    
    return twitter_since_id

################################################################################
def fetchTweets(twiapi, twitter_since_id):
    countLimit = 100
    dict_tweets = {}

    if twitter_since_id == 0:
        tweets = twiapi.GetFriendsTimeline(retweets=True, count=countLimit)
        for tweet in tweets:
            dict_tweets[tweet.GetId()]=tweet
    else:
        page_requested=1
        some_tweets = twiapi.GetFriendsTimeline(retweets=True, count=countLimit, since_id=twitter_since_id, page=page_requested)
        for tweet in some_tweets:
            dict_tweets[tweet.GetId()]=tweet
        
        while len(some_tweets) != 0:
            #Some throttling to avoid hassling twitter's servers
            time.sleep(1)
  
            page_requested += 1
            some_tweets = twiapi.GetFriendsTimeline(retweets=True, count=countLimit, since_id=twitter_since_id, page=page_requested)

            if not dict_tweets.has_key(tweet.GetId()):
                for tweet in some_tweets:
                    dict_tweets[tweet.GetId()]=tweet

    return dict_tweets
################################################################################
def shutdown(imapapi, exitval):
    imapapi.logout()
    sys.exit(exitval)
################################################################################
def getListHashTag(text):        
    list_hashtags = []
    re_hashtag = re.compile("^([a-zA-Z0-9]+)")
    pos = text.find("#")
    while pos != -1:
        text = text[pos + 1:]
        res_hashtag = re_hashtag.match(text)
        if res_hashtag:
            list_hashtags.append(res_hashtag.group(1))
        pos = text.find("#")
    return list_hashtags

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
def generate_email_elmts(tweet_text, user):
    #If the tweet is a retweet, format differently the text "someone said:\n tweet content" and change email subject to "Retweet from"
    if tweet_text[0:2] == "RT":
        subject = "Retweet from @" + user.GetScreenName()
        tweet_table = tweet_text.split(" ")
        tweet_table.pop(0)
        original_author = tweet_table.pop(0)[1:].rstrip(":")
        email_text = original_author + " said:\n" + (" ".join(tweet_table))
    else:
        original_author = user.GetScreenName()
        subject = "Tweet from @" + original_author
        email_text = tweet_text

    return (original_author, subject, email_text)
################################################################################
def extract_hashtags(email_text):
    hashtag_list = getListHashTag(email_text)        
    subject_suffix = ""
    if len(hashtag_list) > 0:
        subject_suffix += " --"
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
 
        user = tweet.GetUser()

        if user.GetDescription():
            user_desc="User Desc= "+ user.GetDescription() + "\n"
        else:
            user_desc=""
        
        tweet_id=str(tweet.GetId())

        (original_author, subject, email_text) = generate_email_elmts(tweet.GetText(), user)

        #Extract hashtags
        subject += extract_hashtags(email_text)

        #Extends short links
        email_text, indexed_links = resolv_short_links(email_text)

        links_text = generate_links_text(indexed_links)

        #Build security token for retweets and replies
        securityTokenConstructor = hmac.new(secret);
        securityTokenConstructor.update(tweet_id)
        securityToken = securityTokenConstructor.hexdigest()

        email = "From: " + preventHeaderInjection(user.GetName()) + " <" + replyBot + ">\n" + \
                "To: <" + myEmailAddress + ">\n" + \
                "Date: " + time.strftime("%a, %d %b %Y %H:%M:%S +0000", time.gmtime(tweet.GetCreatedAtInSeconds())) + "\n" + \
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
                "Twitter link= https://twitter.com/" + original_author + "/status/" + tweet_id + "\n" + \
                h.unescape(user_desc)

        #Send IMAP cmd to store the tweet
        imapapi.append(twitter_mailbox, "(New)", tweet.GetCreatedAtInSeconds(), email.encode('utf-8', 'replace'))

################################################################################
def resolv_short_links(text):
    re_url = re.compile(r"^((?:http|https)?:\/\/[\w\-_]+(?:\.[\w\-_]+)+(?:[\w\-\.,@?^=%&amp;:/~\+#\[\]]*[\w\-\@?^=%&amp;/~\+#\[\]])?)")
    dict_short_links = {}
    indexed_links = []
    remain_text = text
    pos = remain_text.find("http://")
    if pos == -1:
        pos = remain_text.find("https://")
    while pos != -1 :    
        #Loose everything before the link
        remain_text = remain_text[pos:]

        #Find the end of the link 
        url = re_url.match(remain_text)
        if not url: #Huh? http(s):// and not a URL? Stopping resolution... something went ugly here
            break
        end_url_pos = len(url.group(1))

        #Extract the link
        short_link = remain_text[:end_url_pos]

        #Resolv link
        dict_short_links[short_link] = resolv_a_short_link(short_link)

        #Forget the link
        remain_text = remain_text[end_url_pos:]

        #Find next link
        pos = remain_text.find("http://")
        if pos == -1:
            pos = remain_text.find("https://")

    #replacing the short links
    i = 1
    for key in dict_short_links.keys():
        text = text.replace(key, "[Link " + str(i) + "]")
        indexed_links.insert(i, dict_short_links[key])
        i += 1

    return text, indexed_links

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

if __name__ == "__main__":
    twiapi = twitter.Api( consumer_key=consumer_key,
                          consumer_secret=consumer_secret,
                          access_token_key=access_token_key,
                          access_token_secret=access_token_secret
                          )

    if use_ssl:
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
    new_tweets = fetchTweets(twiapi, twitter_since_id)

    if len(new_tweets) == 0:
        shutdown(imapapi, 1)

    #Save tweets to IMAP
    saveTweetsToImap(imapapi, twitter_mailbox, new_tweets, myEmailAddress, replyBot, hashlib.sha256(consumer_key + consumer_secret).hexdigest())

    shutdown(imapapi, 0)

