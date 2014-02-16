import praw
import redis
import sys
import time
import re
import requests
import logging
import gc

logging.basicConfig(level=logging.DEBUG)

def handle_ratelimit(func, *args, **kwargs):
    while True:
        try:
            func(*args, **kwargs)
            break
        except praw.errors.RateLimitExceeded as error:
            logging.debug('\tSleeping for %d seconds' % error.sleep_time)
            time.sleep(error.sleep_time)

pending_cushion = 50
findbal = re.compile('Your current balance is: ([0-9]+[.0-9]*) dogecoins')            
def update_bal(r, dis):
    r.send_message('dogetipbot', '+history', '+history')
    while True:
        mes = r.get_unread(limit=None)
        for m in mes:
            m.mark_as_read()
            if m.author == 'dogetipbot' and m.subject == '+history':
                match = findbal.search(m.body)
                logging.debug('Got reply from dogetipbot with +history!')
                if match and match.group(1):
                    bal = float(match.group(1))
                    if bal <= pending_cushion: #Keep enough for pending tips mayhaps
                        logging.debug('Balance super, super low. For real. :( No more tips.')
                        dis.set('bal', 0)
                    else:
                        logging.debug('Balance is '+str(bal)+', so I can do some tipping!')
                        dis.set('bal', bal-pending_cushion)
                return

DEBUG_ONCE = False

karma_curve = [22, 8, 3, 1]
tip_max_curve=[200, 75, 50, 5]

def next_karma(score):
    for num in karma_curve:           
        if score>=num:
            return num
    return 0
    
banned = ['starcraft', 'news', 'Bitcoin']
conditionally_removed = ['DogeCoinPIF', 'DogeTippingWars', 'DogeTrain']
            
def main(username, password, dis):
    
    r = praw.Reddit('doge_doubling_bot/0.2 by levy')
    r.login(username, password)
    dogetipbot = r.get_redditor('dogetipbot')
    
    est_bal = float(dis.get('bal'))
    if est_bal < 5:
        logging.debug("I only have Ð"+str(est_bal)+", but need at LEAST 5 to tip. Checking in with /u/dogetipbot (this could take awhile).")
        logging.debug("Tip +/u/"+username+" to fill up.")
        update_bal(r, dis)
        if float(dis.get('bal')) < 5:
            raise Exception('Not enough doge!')
        
    logging.debug('My starting balance today is Ð'+str(dis.get('bal'))+', time to spend!')
    
    while float(dis.get('bal')) >= 5:
        
        comments = dogetipbot.get_comments(sort='new', limit=1000)
        
        reg = re.compile('Ð(\d*[.]?\d+) ')
        for elem in comments:
            s = elem.score
            text = elem.body
            place = text.index('Ð')
            if (not place) or (place <= 0): 
                continue
            
            match = reg.search(text[place:])
            if not match: #Did we match a number?
                logging.debug('No Match: ', text)
                continue
                
            parsed = match.group(1)
            if (not parsed) or (not elem.parent_id) or elem.is_root: #did we find it, and does the reply have a parent?
                continue
            
            bal = float(dis.get('bal'))
            if elem.subreddit and (str(elem.subreddit) in banned):
                logging.debug('Won\'t try to post to banned subreddit: ' + str(elem.subreddit))
                continue
            if bal<4000 and (str(elem.subreddit) in conditionally_removed):
                logging.debug('Currently too poor (Ð'+str(bal)+') to feed money into circlejerk subreddit: ' + str(elem.subreddit))
                continue
            
            parent = r.get_info(thing_id=elem.parent_id) 
            if (not parent):
                logging.debug("Thread with no parent")
                continue
            if not parent.author:
                logging.debug("Thread parent with no author!")
                continue
            if (parent.author.name == username): #Did we get the parent okay, is it us?
                logging.debug("Parent was us.")
                continue
            
            num = float(parsed)
            if (bal<5):
                logging.debug("I'm out of doge for now! I've got Ð"+str(bal))
                break
            if (not num) or (not bal) or (num>bal): #Did we get the number, and are our karma restrictions met?
                logging.debug("Either couldn't get balance, or tip wasn't in range, or parent scored too poorly.")
                logging.debug(num, ">", bal)
                continue
                
            #Is it in one of our allowable karma brackets?
                
            karma = next_karma(parent.score)

            if karma==0:
                logging.debug('Post didn\'t have any karma, no doge for it:', parent.score, karma)
                continue
            tip_lim = tip_max_curve[karma_curve.index(karma)]
            if num>tip_lim:
                logging.debug('Karma: %d<=%d, Post value (%d) too high, can\'t match. (Max: %d)' % (karma, parent.score, num, tip_lim))
                continue
            if karma==1 and bal<3000:
                logging.debug('Bal < 3000, too poor to keep blanket-doubling Ð5 tips.')
                continue
                
            # Get the parent's parent and reply to it!
            top_parent = r.get_info(thing_id=parent.parent_id)
            if dis.get(parent.permalink) or (not top_parent) or (not top_parent.author) or (top_parent.author.name == username): #No, we won't double a tip to ourselves.
                logging.debug('trying to not tip ourselves or retip')
                continue
                
            logging.debug(s, "Ð: ", num, parent.score, parent.body)
            logging.debug("Donating to:", top_parent.permalink)
            
            tiptxt = "+/u/dogetipbot "+str(num)+" doge verify"
            warning = "__^This ^bot ^is ^incredibly [^experimental.](http://www.reddit.com/r/dogeducation/comments/1x4ii1/udoge_doubling_bot_and_you_power_to_the_little_tip/)__ ^This ^tip [^was ^caused]("+parent.permalink+") ^by ^+/u/"+parent.author.name
            begging = "*^Want ^this ^bot ^to ^continue ^tipping? ^Just ^tip ^it ^to ^help ^it ^continue ^copying ^tips.*"
            replytxt = tiptxt + '\n***\n' + warning + '\n\n' + begging
            logging.debug(replytxt)
            if parent.is_root:
                handle_ratelimit(top_parent.add_comment, replytxt)
            else:
                handle_ratelimit(top_parent.reply, replytxt)
            dis.set(parent.permalink, num)
            dis.set('bal', bal - num)
            if DEBUG_ONCE:
                break
        
        if DEBUG_ONCE:
            break
        logging.debug('Sleeping for 5 minutes before the next run.')
        dis.save()
        gc.collect()
        time.sleep(5*60)

def rebuild_database(username, password, dis):
    r = praw.Reddit('much_doge_tip_doubler_very_wow')
    r.login(username, password)
    me = r.get_redditor(username)
    coms = me.get_comments(sort='new', limit=None) #Build backwards
    reg = re.compile('\[\^was \^caused\]\((.*)\)')
    balreg = re.compile('\+\/u\/dogetipbot (.*) doge verify')
    
    logging.debug('Finding missing entries...')
    total = 0
    count = 0
    for c in coms:
        txt = c.body
        link = reg.search(txt)
        if not link:
            logging.debug('link not found...')
            continue
        permalink = link.group(1)
        amt = balreg.search(txt)
        if not amt:
            logging.debug('transaction amount not found...')
            continue
        if not dis.get(permalink):
            num = float(amt.group(1))
            dis.set(permalink, num)
            logging.debug('Added Ð'+str(num)+' comment from date '+str(c.created))
            count += 1
            total += num
    
    logging.debug('Making redis save...')    
    dis.save() # Just in case!
    logging.debug('Done resynchronizing! Re-added Ð'+str(total)+' across '+str(count)+' comments!')
        
if __name__ == '__main__':
    if len(sys.argv) < 5:
        logging.debug('expecting: username password redishost redisport [\'rebuild\']')
        sys.ext(0)
    
    if len(sys.argv) > 5 and sys.argv[5]=='rebuild':
        rebuild_database(sys.argv[1], sys.argv[2], redis.StrictRedis(host=sys.argv[3], port=sys.argv[4], db=0))
    
    while True:
        try: 
            main(sys.argv[1], sys.argv[2], redis.StrictRedis(host=sys.argv[3], port=sys.argv[4], db=0))
        except requests.exceptions.HTTPError as err:
            logging.exception("Request error:", err)
            logging.debug("Sleeping for 5 minutes and restarting...")
            time.sleep(5*60);
        except Exception as fault:
            logging.debug("Unhandled fault!")
            logging.exception(fault)
            sys.exit(0)