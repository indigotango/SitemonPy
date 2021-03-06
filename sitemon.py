from datetime import date, timezone
from email.mime.text import MIMEText
from email.utils import make_msgid
from time import strftime
import datetime
import hashlib
import requests
import smtplib
import sqlite3
import yaml

### Configuration options ###
cfg_emailFrom = "SitemonPy@mydomain.net"
cfg_emailTo   = "recipientEmail@mydomain.net"
cfg_emailServer = "smtp.emailhost.xyz"
cfg_emailServerPort = 587

# Define function for console timestamps
def cTimestamp(message):
  print(str(datetime.datetime.now()) + " " + message)

# Define user agent for web requests
myUserAgent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:97.0) " +\
              "Gecko/20100101 Firefox/97.0"
requestsCustomUserAgent = {'user-agent': myUserAgent}

# Get credentials for email + Telegram
try:
  with open(r'secrets.yml') as credentialsFile:
    credentialsYAML = yaml.safe_load(credentialsFile)
    credentials = credentialsYAML['secrets']
except IOError:
  raise    

# Get list of target sites to examine
try:
  with open(r'targets.yml') as targetListFile:
    targetsYAML = yaml.safe_load(targetListFile)
except IOError:
  raise

# Connect to database (SQLite)
db = sqlite3.connect('sitemonpy.db')
dbCursor = db.cursor()

# Exctract list of target sites
targets = targetsYAML['targets']
cTimestamp("[i] Site targets loaded: " + str(len(targets)))

# Process each target site
for site in targets:
  # Ensure log file exists, else throw exception
  #try:
  #  with open('logs/' + site + '.txt', 'a') as logFile:
  #    cTimestamp("[*] Loaded log file for target: " + site)
  #except IOError:
  #  raise

  # Retrieve site contents
  siteContentRaw = requests.get(targets[site], headers=requestsCustomUserAgent)
  requestTimestamp = str(datetime.datetime.now())
  
  # Generate hash of site content + output as typical hex
  contentHash = hashlib.sha256(siteContentRaw.content).hexdigest()
  
  # Get from database the last hash for target sites
  # SQL: get all columns for item, sort items in reverse order, limit to 1 item
  # NOTE: "rowid" field is implicit in SQLite, it is the table row's ID
  dbQuerySelect = dbCursor.execute(
    "SELECT hash FROM logs WHERE target=:target ORDER BY rowid DESC LIMIT 1",
    {"target": site}
  )
  # Retrieve result row (there should only be 1 row)
  # "[0]" indicates the first item of the list object (the hash)
  lastHash = dbQuerySelect.fetchone()[0]

  # Handle missing database entries (i.e. if no content hashes for target)
  if(len(lastHash)) < 1:
    cTimestamp("[!] No content hashes in database for site " + site)
    cTimestamp("[+] Saving current hash to database and going to next target")
    break # Drop out of current loop iteration and go to next target, or exit

  # Insert refreshed hash (regardless if new or still current) into database
  dbQueryInsert = dbCursor.execute(
      "INSERT INTO logs (target, hash, timestamp) " +\
      "VALUES (:target, :hash, :timestamp)",
      {
        "target": site,
        "hash": contentHash,
        "timestamp": requestTimestamp
      }
    )
  # Commit row to database
  db.commit()
  
  # Compare hashes + take appropriate action
  if contentHash == lastHash:
    # No changes to page content were detected
    cTimestamp("[+] No content changes detected for target: " + site)
  
  else:
    # Site content change is detected!
    cTimestamp("[+] Content change detected for " + site +\
            ", new hash: " + contentHash)
    
    # Send notification via email
    cTimestamp("[i] Sending email notification for " + site)

    msgHeader  = "SitemonPy content change notification\n\n"
    msgTarget  = "Target: " + targets[site] + "\n"
    msgOldHash = "Old hash: " + lastHash + "\n"
    msgNewHash = "New hash: " + contentHash + "\n"
    msgTimestamp = "Timestamp: " + requestTimestamp

    mailMsg = MIMEText(
      msgHeader + msgTarget + msgOldHash + msgNewHash + msgTimestamp
    )
    mailMsg['Message-ID'] = make_msgid(
                            # See email.utils import
                            idstring = "sentWithSitemonPy",
                            domain = "sitemon.py_script"
                            ) 
    mailMsg['Subject'] = "SitemonPy - " + site + " - Content change detected"
    mailMsg['Date']    = str(datetime.datetime.now(timezone.utc))
    mailMsg['From']    = cfg_emailFrom
    mailMsg['To']      = cfg_emailTo
  
    with smtplib.SMTP(cfg_emailServer, cfg_emailServerPort) as mailServer:
      mailServer.starttls()
      mailServer.login(credentials['emailUser'], credentials['emailPswd'])
      mailServer.sendmail(mailMsg['From'], mailMsg['To'], mailMsg.as_string())
    cTimestamp("[+] Email notification sent!")

    # Send notification via Telegram message
    cTimestamp("[i] Sending Telegram message notification for " + site)

    # Telegram API: for newline, use '%0A' in place of \n or <br>
    tgMsg = "<u>SitemonPy</u>%0A" +\
            "???? A change to a target site's content was detected:%0A" +\
            "<b>Target</b>: " + targets[site] + "%0A" +\
            "<b>Timestamp</b>: " + requestTimestamp + " AK time%0A" +\
            "Old hash: " + lastHash + "%0A" +\
            "New hash: " + contentHash
    
    tgMsgReq = "https://api.telegram.org/bot" + credentials['tgBotToken'] +\
               "/sendMessage?chat_id=" + credentials['tgGroupChatID'] +\
               "&parse_mode=HTML&text=" + str(tgMsg)
    tgMsgSend = requests.get(tgMsgReq)
    cTimestamp("[+] Telegram message sent!")

# Close database when complete
cTimestamp("[i] All done. Closing database...")
dbCursor.close()
db.close()
cTimestamp("[x] ... k bye!")
