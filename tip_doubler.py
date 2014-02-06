import praw
import redis
import sys
import time
import re
import requests

def handle_ratelimit(func, *args, **kwargs):
    while True:
        try:
            func(*args, **kwargs)
            break
        except praw.errors.RateLimitExceeded as error:
            print('\tSleeping for %d seconds' % error.sleep_time)
            time.sleep(error.sleep_time)

tip_limit = 50
karma_minimum = 6
DEBUG_ONCE = False
            
def main(username, password, dis):

    est_bal = float(dis.get('bal'))
    if est_bal < 5:
        print("I only have Ð"+str(est_bal)+", but need at LEAST 5 to tip. Goodbye.")
        print("Tip +/u/"+username+" to fill up.")
        raise Exception('Not enough doge!')
        
    print('My starting balance today is Ð'+str(est_bal)+', time to spend!')
    
    r = praw.Reddit('doge_doubling_bot/0.2 by levy')
    r.login(username, password)
    dogetipbot = r.get_redditor('dogetipbot')
    
    while float(dis.get('bal')) >= 5:
        
        comments = dogetipbot.get_comments(sort='hot', time='new', limit=200)
        
        reg = re.compile('Ð(\d*[.]?\d+) ')
        for elem in comments:
            s = elem.score
            text = elem.body
            place = text.index('Ð')
            if (not place) or (place <= 0): 
                continue
            
            match = reg.search(text[place:])
            if not match: #Did we match a number?
                print('No Match: ', text)
                continue
                
            parsed = match.group(1)
            if (not parsed) or (not elem.parent_id) or elem.is_root: #did we find it, and does the reply have a parent?
                continue
            
            parent = r.get_info(thing_id=elem.parent_id) 
            if (not parent):
                print("Thread with no parent")
                continue
            if not parent.author:
                print("Thread parent with no author!")
                continue
            if (parent.author.name == username): #Did we get the parent okay, is it us?
                print("Parent was us.")
                continue
            
            num = float(parsed)
            bal = float(dis.get('bal'))
            if (bal<5):
                print("I'm out of doge for now! I've got Ð"+bal)
                break
            if (not num) or (not bal) or (num>bal) or (num>tip_limit) or parent.score<karma_minimum: #Did we get the number, and are our karma restrictions met?
                print("Either couldn't get balance, or tip wasn't in range, or parent scored too poorly.")
                print("Parent score:", parent.score)
                print(num, ">", tip_limit, "or", bal)
                continue
                
            # Get the parent's parent and reply to it!
            top_parent = r.get_info(thing_id=parent.parent_id)
            if dis.get(parent.permalink) or (not top_parent) or (top_parent.author.name == username): #No, we won't double a tip to ourselves.
                print('trying to not tip ourselves or retip')
                print('Retip status:', dis.get(parent.permalink))
                print('Self-donation status:', top_parent.author.name == username)
                continue
                
            print(s, "Ð: ", num, parent.score, parent.body)
            print("Donating to:", top_parent.permalink)
            
            tiptxt = "+/u/dogetipbot "+str(num)+" doge verify"
            warning = "__^This ^bot ^is ^incredibly ^experimental.__ ^This ^tip [^was ^caused]("+parent.permalink+") ^by ^+/u/"+parent.author.name
            begging = "*^Want ^this ^bot ^to ^continue ^tipping? ^Just ^tip ^it ^to ^help ^it ^continue ^copying ^tips.*"
            replytxt = tiptxt + '\n***\n' + warning + '\n\n' + begging
            print(replytxt)
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
        print('Sleeping for 5 minutes before the next run.')
        dis.save()
        time.sleep(5*60);

def rebuild_database(username, password, dis):
    r = praw.Reddit('much_doge_tip_doubler_very_wow')
    r.login(username, password)
    me = r.get_redditor(username)
    coms = me.get_comments(sort='new', limit=None) #Build backwards
    reg = re.compile('\[\^was \^caused\]\((.*)\)')
    balreg = re.compile('\+\/u\/dogetipbot (.*) doge verify')
    
    print('Finding missing entries...')
    total = 0
    count = 0
    for c in coms:
        txt = c.body
        link = reg.search(txt)
        if not link:
            print('link not found...')
            continue
        permalink = link.group(1)
        amt = balreg.search(txt)
        if not amt:
            print('transaction amount not found...')
            continue
        if not dis.get(permalink):
            num = float(amt.group(1))
            dis.set(permalink, num)
            print('Added Ð'+str(num)+' comment from date '+str(c.created))
            count += 1
            total += num
    
    print('Making redis save...')    
    dis.save() # Just in case!
    print('Done resynchronizing! Re-added Ð'+str(total)+' across '+str(count)+' comments!')
        
if __name__ == '__main__':
    if len(sys.argv) < 5:
        print('expecting: username password redishost redisport [\'rebuild\']')
        sys.ext(0)
    
    if len(sys.argv) > 5 and sys.argv[5]=='rebuild':
        rebuild_database(sys.argv[1], sys.argv[2], redis.StrictRedis(host=sys.argv[3], port=sys.argv[4], db=0))
    
    while True:
        try: 
            main(sys.argv[1], sys.argv[2], redis.StrictRedis(host=sys.argv[3], port=sys.argv[4], db=0))
        except requests.exceptions.HTTPError as err:
            print("Request error:", err)
            print("Sleeping for 5 minutes and restarting...")
            time.sleep(5*60);
        except Exception as fault:
            print("Unhandled fault!")
            print(fault)
            sys.exit(0)