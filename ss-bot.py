# coding=utf-8
import json
import requests
import urllib
import time
import re
import nltk
import urllib
import os

TOKEN = os.environ['TOKEN']
URL = "https://api.telegram.org/bot{}/".format(TOKEN)
DOWNLOAD_URL = "https://api.telegram.org/file/bot{}/".format(TOKEN)

locations = dict()


def get_url(url):
    response = requests.get(url)
    content = response.content.decode("utf8")
    return content


def get_json_from_url(url):
    content = get_url(url)
    js = json.loads(content)
    return js


def get_updates(offset=None):
    url = URL + "getUpdates?timeout=100"
    if offset:
        url += "&offset={}".format(offset)
    js = get_json_from_url(url)
    return js

def get_last_update_id(updates):
    update_ids = []
    for update in updates["result"]:
        update_ids.append(int(update["update_id"]))
    return max(update_ids)


def get_last_chat_id_and_text(updates):
    num_updates = len(updates["result"])
    last_update = num_updates - 1
    text = updates["result"][last_update]["message"]["text"]
    chat_id = updates["result"][last_update]["message"]["chat"]["id"]
    return (text, chat_id)

def get_status_alert(id, chat):
    alert_url = 'http://tess-dashboards.stars4all.eu/api/alerts/'

    alerts = get_json_from_url(alert_url)
    for alert in alerts:
        if id in alert["name"]:
            message = alert["name"]+ " -> " +alert["state"]
            send_message(message,chat)

def get_nouns(sentence):
    tokens = nltk.word_tokenize(sentence)
    tagged = nltk.pos_tag(tokens)

    words = []

    for (word, tag) in tagged:
        if tag == "NNS" or tag == "NN" or tag == "NNP" or tag == "NNPS":
            words.append(word)

    return words

def send_message(text, chat_id, reply_markup=None):
    #text = urllib.parse.quote_plus(text)
    text.replace(" ","+")
    url = URL + "sendMessage?text={}&chat_id={}&parse_mode=Markdown".format(text, chat_id)
    if reply_markup:
        url += "&reply_markup={}".format(reply_markup)
    get_url(url)

keyboard_wait = ['Let\'s go!','Más info sobre el proyecto','Denunciar incidencia','Salir']
keyboard_menu = ['Let\'s go!','More info']
keyboard_location = ['Take a photo']
keyboard_color = ['blue','white','orange']

def handle_updates(updates):
    message=''
    for update in updates["result"]:
        print (update)
        if 'message' in update:
            message = update["message"]
            if 'location' in message:
                handle_location(message,False)
        if 'edited_message' in update:
            message = update["edited_message"]
            if 'location' in message:
                handle_location(message,True)

        if 'text' in message:
            handle_text(update)
        if 'photo' in message:
            handle_photo(message)



def handle_photo(message):
    chat = message["chat"]["id"]
    file_id = message["photo"][2]["file_id"]
    get_file_url = URL+"getFile?file_id={}".format(file_id)

    file = get_json_from_url(get_file_url)

    download_url = DOWNLOAD_URL+"{}".format(file["result"]["file_path"]) # We should index this data
    print("***********************New Image*************************+")
    print(locations[message["from"]["id"]])
    print(download_url)

    #f = open(str(file_id)+".jpg", 'wb')
    #f.write(urllib.urlopen(download_url).read())
    #f.close()
    send_message("Thank you!", chat)
    #response_image = urllib.urlretrieve(download_url, str(file_id)+".jpg")
    send_message("Your image has been registered in our system", chat)
    keyboard = build_keyboard(keyboard_color)
    send_message("What is the color of the light?", chat,keyboard)


def handle_location(message, realtime):
    chat = message["chat"]["id"]
    user_id = message["from"]["id"]
    keyboard = build_keyboard(keyboard_location)
    if not realtime:
        send_message("Great!",chat)
        send_message("Now, place your grating in front of the camera and take a photo", chat, keyboard)
    print(message["location"])
    locations[user_id] = message["location"]

def handle_text(update):
        try:
            text = update["message"]["text"]
            chat = update["message"]["chat"]["id"]
            date = update["message"]["date"]
            first_name = update["message"]["from"]["first_name"]

            text = text.encode('utf-8')

            if text == "/start":
                keyboard = build_keyboard(keyboard_menu)
                send_message("Hi {}, I am STREET SPECTRA, your mapping assistant. What do you need?".format(first_name), chat, keyboard)

            if 'hi' in text.lower():
                keyboard = build_keyboard(keyboard_menu)
                send_message('Hi.',chat, keyboard)
                send_message('How can I help you?', chat, keyboard)

            if 'status' in text:
                photometer_list = re.findall(r'\bstars\w+',text)
                if photometer_list != []:
                    for photometer in photometer_list:
                        get_status_alert(photometer, chat)
                else:
                    words = get_nouns(text.encode('utf-8'))
                    for word in words:
                        get_status_alert(word, chat)
                    if words == []:
                        send_message('Could you specify a photometer?',chat)

            if 'Let\'s go!' in text:
                send_message("Share your real time location with us by clicking in the clip button.",chat)

            if 'Take a photo' in text:
                keyboard = build_keyboard(keyboard_location)
                send_message("Now, place your grating in front of the camera and take a photo", chat, keyboard)

            if text == 'More info':
                keyboard = build_keyboard(keyboard_menu)
                send_message("This bot is an initiative of the ACTION project. With its help, you can map the lampposts of your city and collaborate to study the impact of the light pollution")

            if 'yes' in text.lower():
                keyboard = build_keyboard(keyboard_menu)
                send_message("Move to another lamppost and send us your location", chat, keyboard)

            if 'no' in text.lower():
                keyboard = build_keyboard(keyboard_menu)
                send_message("Thank you for your contribution", chat, keyboard)


        except Exception as e:
            print(e)
            try:
                date = update["message"]["date"]
                chat = update["message"]["chat"]["id"]
                send_message('I do not understand your message',chat)

            except Exception as e:
                print(e)

def build_keyboard(items):
    keyboard = [[item] for item in items]
    reply_markup = {"keyboard":keyboard, "one_time_keyboard": True}
    return json.dumps(reply_markup)

def main():
    last_update_id = None
    while True:
        updates = get_updates(last_update_id)
        if len(updates["result"]) > 0:
            last_update_id = get_last_update_id(updates) + 1
            handle_updates(updates)
        time.sleep(0.5)


if __name__ == '__main__':
    main()

