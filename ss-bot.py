# coding=utf-8
import json
import requests
import random
import urllib
import time
import re
import nltk
import datetime
import os
import logging
import logging.config

from suntime import Sun, SunTimeException
from timezonefinder import TimezoneFinder
import pytz

TOKEN = "1290123918:AAHozYmKK3QNZ8dGMdkvaswYDHaNPUovqJE" #os.environ['TOKEN']
URL = "https://api.telegram.org/bot{}/".format(TOKEN)
DOWNLOAD_URL = "https://api.telegram.org/file/bot{}/".format(TOKEN)


locations = dict()
logging.config.fileConfig('ss-telegram-bot-master/config/logging.cfg')  # logfile config, logging.config.fileConfig('config/logging.cfg') si fuera de heroku

status = dict()

time_zone = None

observations = dict()

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

def send_photo(caption, photo, chat_id, reply_markup=None):
    caption.replace(" ","+")
    url = URL + "sendPhoto?caption={}&photo={}&chat_id={}".format(caption, photo, chat_id)
    if reply_markup:
        url += "&reply_markup={}".format(reply_markup)
    get_url(url)


keyboard_wait = ['Let\'s go!','Más info sobre el proyecto','Denunciar incidencia','Salir']
keyboard_menu = ['Let\'s go!', 'Classify', 'About','Help']
keyboard_tutorial = ['Start tutorial','Exit']
keyboard_tutorial_step1 = ['Tip 1','Exit']
keyboard_tutorial_step2 = ['Tip 2','Exit']
keyboard_tutorial_finish = ['Finish']
keyboard_new = ['Send a new one', "Finish"]
keyboard_classify = ['Classify a new one', "Finish"]
keyboard_photo = ['This lamppost is of a different type than the previous one', "This lamppost is the same type as the previous one"]
keyboard_color_day = ['white','orange']
keyboard_color_night = ['HPS', 'LPS', 'LED', 'MV', 'MH']

def handle_updates(updates):
    message=''
    for update in updates["result"]:
        logging.info(update)
        if 'message' in update:
            message = update["message"]
            if 'location' in message:
                handle_location(message,False)
        if 'edited_message' in update:
            logging.info("edited_message")
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
    logging.info("***********************New Image*************************+")
    if message["from"]["id"] in locations:
        logging.info(locations[message["from"]["id"]])
    else:
        logging.error("No location point")
    logging.info(download_url)

    user_id = message["from"]["id"]
    if user_id in observations:
        observation = observations[user_id]
        observation["image_url"] = download_url
        observation["date"] = message["date"]
        observations[user_id] = observation
    else:
        observations[user_id] = {"image_url": download_url+str(file_id)+".jpg","date":message["date"]}

    send_message("Thank you!", chat)

    try:

        time_zone = observations[user_id]["time_zone"]
        response_image = urllib.request.urlretrieve(download_url, str(file_id)+".jpg")
        #send_message("Your image has been registered in our system", chat)
        
        if time_zone == "Day":
            keyboard = build_reply_keyboard(keyboard_color_day)
            send_message("What is the color of the light?", chat,keyboard)
        elif time_zone == "Night":
            keyboard = build_reply_keyboard(keyboard_color_night)
            send_message("What is the type of light?", chat,keyboard)


    except Exception as e:
        logging.error(e)


#TODO: Asumimos que el usuario nos compartió su realtime. Si no lo hace o caduca, estaremos cogiendo
# la última siempre hasta que vuelva a decir un Hi

def handle_location(message, realtime):
    chat = message["chat"]["id"]
    user_id = message["from"]["id"]
    latitude = message["location"]["latitude"]
    longitude = message["location"]["longitude"]

    day = get_timezone(latitude, longitude)

    if not realtime:
        send_message("Great!",chat)

        if day == "Day":
            send_message("Awesome, you can take a photo now.",chat)
        else:
            send_message("Awesome, place your grating in front of the camera and take a photo.",chat)


    logging.info(message["location"])
    locations[user_id] = message["location"]
    if user_id in observations:
        observation =  observations[user_id]
        observation["latitude"] = message["location"]["latitude"]
        observation["longitude"] = message["location"]["longitude"]
        observations["time_zone"] = day
        observations[user_id] = observation
    else:
        observations[user_id] = {"latitude":message["location"]["latitude"],"longitude":message["location"]["longitude"], "time_zone":day}

    logging.info("location changed:"+str(observations[user_id]))

def send_observation(user):

    logging.info("------- NEW OBSERVATION ------")
    logging.info(",".join(("{}={}".format(*i) for i in observations[user].items())))

    #TODO: Descomentar para enviar a API

    #observation = {"datasource": "telegram", "userid": user, "observation": observations[user]}
    
    #response = requests.post("https://api.actionproject.eu/observations", json=observation)

    #logging.info(response)

def get_observation(user):

    response = requests.get("https://api.actionproject.eu/observations")

    response_json = json.loads(response.text)

    logging.info(response_json)

    rand_num = randrange(len(response_json))

    return response_json[rand_num]

def handle_text(update):
        try:
            text = update["message"]["text"]
            chat = update["message"]["chat"]["id"]
            date = update["message"]["date"]
            first_name = update["message"]["from"]["first_name"]
            user_id = update["message"]["from"]["id"]

            #text = text.encode('utf-8') Añade b' al inicio del string y da problemas al enviar el mensaje

            if text == "/start":
                keyboard = build_keyboard(keyboard_menu)
                send_message("Hi {}, I am STREET SPECTRA, your mapping assistant. What do you need?".format(first_name), chat, keyboard)

            if 'hi' == text.lower():
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
                #location_keyboard = telegram.KeyboardButton(text="send_location", request_location=True)

                #reply_markup = {"keyboard": [["send_location"]],"request_location":True, "one_time_keyboard": True}
                #keyboard = json.dumps(reply_markup)
                send_message("Share your realtime location with us by clicking in the clip button.",chat)

            #Only send night photos for classifying  
            if 'Classify' in text:
                keyboard = build_keyboard(keyboard_color_night)
                send_message('I will send you a photo for you to classify it', chat)

                #TODO: revisar forma de acceder a la respuesta en funcion de la estructura de las observaciones
                #to_classify = get_observation()["observation"]
                #photo_url = to_classify['image']

                to_classify = {"latitude": "40.416011","longitude": "-3.672166", "time_zone":"Night", "color": "HPS", "image_url": "https://streetspectra.actionproject.eu/wp-content/uploads/2020/02/action-street-spectra-5.jpeg" , "date":"1593951233", "classification": "yes"}
                photo_url = "https://streetspectra.actionproject.eu/wp-content/uploads/2020/02/action-street-spectra-5.jpeg"
                
                send_photo("What is the type of light?", photo_url, chat, keyboard)

                #TODO: estoy enviando las clasificaciones con el mismo formato de las observaciones con un POST y cambiando el user_id y el color que tenian
                if user_id in observations:
                    observation = observations[user_id]
                    observation = to_classify
                    observations[user_id] = observation
                else:
                    observations[user_id] = to_classify

              
            if text == 'About':
                keyboard = build_keyboard(keyboard_menu)
                send_message("This bot is an initiative of the ACTION project. With its help, you can map the lampposts of your city and collaborate to study the impact of the light pollution",chat)

            if 'help' in text.lower():
                keyboard = build_keyboard(keyboard_tutorial)
                send_message('To use this bot, you have to activate your location', chat)
                send_message("and start to send images of the lamppost spectra", chat)
                send_message("Do not forget to place the grating in front of the camera at night", chat, keyboard)

            if 'Start tutorial' in text:
                keyboard = build_keyboard(keyboard_tutorial_step1)
                send_message('This is a quick tutorial to help you identifying lampposts types', chat)
                send_message("I will send you a few classified photos", chat, keyboard)

            #TODO: Probar en servidor final, en heroku no carga las imagenes
            if 'Tip 1' in text:
                keyboard = build_keyboard(keyboard_tutorial_step2)
                send_message("I will start by sending you photos taken during the day", chat, keyboard)
                send_photo("This is a white lamppost", 'ss-telegram-bot-master/assets/WHITE.png', chat)
                send_photo("And this is an orange one",'ss-telegram-bot-master/assets/ORANGE.png', chat)

            if 'Tip 2' in text:
                keyboard = build_keyboard(keyboard_tutorial_finish)
                send_message("Now I will send you photos taken during the night", chat, keyboard)
                send_photo("This is a HPS lamppost", 'ss-telegram-bot-master/assets/HPS.png', chat)
                send_photo("This is a LPS lamppost", 'ss-telegram-bot-master/assets/LPS.png', chat)
                send_photo("This is a LED lamppost", 'ss-telegram-bot-master/assets/LED.png', chat)
                send_photo("This is a MV lamppost", 'ss-telegram-bot-master/assets/MV.png', chat)
                send_photo("And finally, this is a MH lamppost", 'ss-telegram-bot-master/assets/MH.png', chat)

            if ('Exit' or 'Finish') in text:
                keyboard = build_keyboard(keyboard_menu)
                send_message('How can I help you?', chat, keyboard)

            if 'Send a new one' in text:
                
                keyboard = build_keyboard(keyboard_photo)
                send_message("Choose an option when you find a new lamppost.",chat, keyboard)

            if 'Finish' in text:
                del observations[user_id]
                send_message("See you soon! Say Hi whenever you want to send new observations.",chat)

            if 'This lamppost is of a different type than the previous one' in text:

                time_zone = observations[user_id]["time_zone"]
                
                if time_zone == "Day":
                    send_message("Awesome, you can take a photo now.",chat)
                else:
                    send_message("Awesome, place your grating in front of the camera and take a photo.",chat)

                
            if 'This lamppost is the same type as the previous one' in text:

                send_observation(user_id)
                keyboard = build_keyboard(keyboard_new)
                send_message("Your observation has been registered", chat)
                send_message("Do you want to send a new one?", chat, keyboard)


            if text == 'white' or text =='orange':
                observation = observations[user_id]
                observation["color"] = text
                observations[user_id] = observation
                send_observation(user_id)
                keyboard = build_keyboard(keyboard_new)
                send_message("Your observation has been registered", chat)
                send_message("Do you want to send a new one?", chat, keyboard)

            if text == 'HPS' or text =='LPS' or text =='LED' or text =='MH' or text =='MV':

                observation = observations[user_id]

                classification = 0 #0 for normal, 1 for cassification

                if "classification" in observation:
                    del observation["classification"]
                    classification = 1

                observation["color"] = text               
                observations[user_id] = observation

                send_observation(user_id)
                send_message("Your observation has been registered", chat)

                if classification == 1:
                    keyboard = build_keyboard(keyboard_classify)
                    send_message("Do you want to classify a new one?", chat, keyboard)
                else:
                    keyboard = build_keyboard(keyboard_new)
                    send_message("Do you want to send a new one?", chat, keyboard)


        except Exception as e:
            logging.error(e)
            try:
                date = update["message"]["date"]
                chat = update["message"]["chat"]["id"]
                send_message('I do not understand your message',chat)

            except Exception as e:
                logging.error(e)

def get_timezone(latitude, longitude):
    #Get today sunrise and sunset
    sun = Sun(latitude, longitude)
    today_sr = int(sun.get_sunrise_time().strftime('%H'))
    today_ss = int(sun.get_sunset_time().strftime('%H'))

    #Get timezone
    tf = TimezoneFinder()
    timezone = tf.timezone_at(lng=longitude, lat=latitude) # returns 'Europe/Berlin'

    #Get time
    tz = pytz.timezone(timezone)
    timezone_now = int(datetime.datetime.now(tz).strftime('%H'))

    logging.info(str(timezone_now))
    logging.info(str(today_sr))
    logging.info(str(today_ss))

    if timezone_now > today_sr and timezone_now < today_ss:
        day = "Day"
    else:
        day = "Night"

    return day


def build_keyboard(items):
    keyboard = [[item] for item in items]
    reply_markup = {"keyboard":keyboard, "one_time_keyboard": True}
    return json.dumps(reply_markup)

def build_reply_keyboard(items):
    keyboard = [[item] for item in items]
    reply_markup = {"keyboard":keyboard, "one_time_keyboard": True, "force_reply": True}
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
