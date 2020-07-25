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
import boto3
from botocore.exceptions import NoCredentialsError

from suntime import Sun, SunTimeException
from timezonefinder import TimezoneFinder
import pytz

TOKEN = #os.environ['TOKEN']
URL = "https://api.telegram.org/bot{}/".format(TOKEN)
DOWNLOAD_URL = "https://api.telegram.org/file/bot{}/".format(TOKEN)
TUTORIAL_URL = "https://github.com/carloscameogbrt/ss-telegram-bot/blob/master/assets/"

#S3
ACCESS_KEY = #os.environ['ACCESSKEYS3']
SECRET_KEY = #os.environ['SECRETKEYS3']
BUCKET_BASE = 'https://tfm-telegram-bot.s3.eu-central-1.amazonaws.com/'


locations = dict()
logging.config.fileConfig('ss-telegram-bot/config/logging.cfg')  # logfile config, logging.config.fileConfig('config/logging.cfg') si fuera de heroku

status = dict()

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

#Las fotos del tutorial cargan desde el github
def send_photo(caption, photo, chat_id, reply_markup=None):
    caption.replace(" ","+")
    url = URL + "sendPhoto?caption={}&photo={}&chat_id={}".format(caption, photo, chat_id)
    if reply_markup:
        url += "&reply_markup={}".format(reply_markup)
    get_url(url)


keyboard_wait = ['Let\'s go!','Más info sobre el proyecto','Denunciar incidencia','Salir']
keyboard_menu = ['Let\'s go!', 'Classify', 'About','Help', 'Privacy policy']
keyboard_tutorial = ['Start tutorial','Exit']
keyboard_tutorial_step1 = ['Tip 1','Exit']
keyboard_tutorial_step2 = ['Tip 2','Exit']
keyboard_tutorial_finish = ['Exit']
keyboard_new = ["Send a new observation of the same type as the previous one", "Send a new observation of a different type than the previous one", "Finish"]
keyboard_classify = ['Classify a new one', "Finish"]
keyboard_color_day = ['white','orange']
keyboard_color_night = ['High Pressure Sodium', 'Low Pressure Sodium', 'Light-Emitting Diode Lamps', 'Mercury Vapor', 'Metal Halide', 'No spectra']

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

    try:

        response_image, headers = urllib.request.urlretrieve(download_url, str(file_id)+".jpg")
        logging.info(response_image)

        uploaded = upload_to_aws(response_image, 'tfm-telegram-bot', str(message["date"]) +".jpg")

        final_url = BUCKET_BASE + str(message["date"]) + ".jpg"

        logging.info(final_url)

        user_id = message["from"]["id"]
        if user_id in observations:
            observation = observations[user_id]
            observation["image_url"] = final_url
            observation["date"] = str(message["date"])
            observations[user_id] = observation
        else:
            observations[user_id] = {"image_url": final_url, "date": str(message["date"])}

        send_message("Thank you!", chat)

        time_zone = observations[user_id]["time_zone"]

        #send_message("Your image has been registered in our system", chat)
        
        if time_zone == "Day":
            keyboard = build_reply_keyboard(keyboard_color_day)
            send_message("What is the color of the light?", chat,keyboard)
        elif time_zone == "Night":
            keyboard = build_reply_keyboard(keyboard_color_night)
            send_message("What is the light source associated to this spectra?", chat,keyboard)


    except Exception as e:
        logging.error(e)


#TODO: Asumimos que el usuario nos compartió su realtime. Si no lo hace o caduca, estaremos cogiendo
# la última siempre hasta que vuelva a decir un Hi
# SOLUCION: Guardar el timestamp del ultimo edited_message y que cuando nos llegue la siguiente observación que no sea de envio a la API, revisar que han pasado más de 5 minutos (poner como parametro)
# desde el timestamp del editedmessage y si es asi , recordarle
# que nos mande la ubicacion en tiempo real. 

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

def send_observation(user, classification):

    logging.info("------- NEW OBSERVATION ------")
    logging.info(",".join(("{}={}".format(*i) for i in observations[user].items())))

    if classification == 1:
        observation = {"project": "street-spectra", "datasource": "telegram", "action": "classify", "userid": user, "observation": observations[user]}
    else:
        observation = {"project": "street-spectra", "datasource": "telegram", "action": "observe", "userid": user, "observation": observations[user]}
    
    header = {'Authorization': 'Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJpYXQiOjE1ODk5NzEyOTgsIm5iZiI6MTU4OTk3MTI5OCwianRpIjoiYTE5MzM2MTUtZmQ5NS00ODFlLWJmY2YtMjkyYTUxZDRiNGU0IiwiZXhwIjoxNTkyNTYzMjk4LCJpZGVudGl0eSI6IlBydWViYSIsImZyZXNoIjpmYWxzZSwidHlwZSI6ImFjY2VzcyJ9.ZJrBt9R0v0ZcKc9kI_6jwFCbRZECvmM6h24jafPx7m8'}

    response = requests.post("https://api.actionproject.eu/observations", json=observation, headers=header)

    logging.info(response)

def get_observation():

    response = requests.get("https://api.actionproject.eu/observations?project=street-spectra")

    response_json = json.loads(response.text)

    logging.info(response_json)

    rand_num = random.randrange(len(response_json))

    logging.info("RANDNUM")
    logging.info(rand_num)

    return response_json[rand_num]

def handle_text(update):
        try:
            text = update["message"]["text"]
            chat = update["message"]["chat"]["id"]
            date = str(update["message"]["date"])
            first_name = update["message"]["from"]["first_name"]
            user_id = update["message"]["from"]["id"]

            #text = text.encode('utf-8') Añade b' al inicio del string y da problemas al enviar el mensaje

            if text == "/start":
                keyboard = build_keyboard(keyboard_menu)
                send_message("Hi {}, I am STREET SPECTRA, your mapping assistant. What do you need?".format(first_name), chat, keyboard)

            if 'hi' == text.lower():
                keyboard = build_keyboard(keyboard_menu)
                send_message('Hi.',chat, keyboard)
                send_message('By continuing you accept that the following personal data: your Telegram ID and the location (latitude and longitude) of your device when sending each observation, will be available to the public and will be used for research purposes within the ACTION STREET SPECTRA Project.',chat, keyboard)
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

            if 'Privacy policy' in text:

                send_message("You can check our Privacy Policy at https://actionproject.eu/privacy-policy/",chat)

            #Only send night photos for classifying  
            if 'Classify' in text:
                keyboard = build_keyboard(keyboard_color_night)
                send_message('I will send you a photo for you to classify it', chat)

                # Esto sirve en el caso de que recibamos observaciones heterogéneas, no es el caso puesto que filtro por project street-spectra, que son las mias
                # while "observation" in to_classify == False:
                #     to_classify = get_observation()

                # to_classify = to_classify["observation"]

                # logging.info("Classify 1/2 - ")
                # logging.info(to_classify)

                # while ("image_url" in to_classify) == False or ("latitude" in to_classify) == False or ("longitude" in to_classify) == False:
                #     to_classify = get_observation()["observation"]
                #     logging.info("Classify 2/2 - ")
                #     logging.info(to_classify)

                to_classify = get_observation()["observation"]

                #TODO: QUITAR CUANDO BORREMOS PRUEBAS DE PROJECT TFM EN LA BASE DE DATOS
                while ("s3" not in to_classify['image_url']) == True or ("1595001962" in to_classify['image_url']) == True:
                    to_classify = get_observation()["observation"]
                #QUITAR HASTA AQUI
                

                photo_url = to_classify['image_url']

                to_classify["time_zone"] = "Night"
                to_classify["date"] = date
                to_classify["classification"] = "yes"

                logging.info(photo_url)

                #{"latitude": "40.416011","longitude": "-3.672166", "time_zone":"Night", "color": "High Pressure Sodium", "image_url": "https://streetspectra.actionproject.eu/wp-content/uploads/2020/02/action-street-spectra-5.jpeg" , "date":"1593951233", "classification": "yes"}
                #photo_url = "https://streetspectra.actionproject.eu/wp-content/uploads/2020/02/action-street-spectra-5.jpeg"
                
                send_photo("What is the light source associated to this spectra?", photo_url, chat, keyboard)

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
                send_photo("This is a white lamppost", TUTORIAL_URL + 'WHITE.png?raw=true', chat)
                send_photo("And this is an orange one", TUTORIAL_URL + 'ORANGE.png?raw=true', chat)

            if 'Tip 2' in text:
                keyboard = build_keyboard(keyboard_tutorial_finish)
                send_message("Now I will send you photos taken during the night", chat, keyboard)
                send_photo("This is a High Pressure Sodium lamppost", TUTORIAL_URL + 'HPS.png?raw=true', chat)
                send_photo("This is a Low Pressure Sodium lamppost", TUTORIAL_URL + 'LPS.png?raw=true', chat)
                send_photo("This is a Light-Emitting Diode Lamps lamppost", TUTORIAL_URL + 'LED.png?raw=true', chat)
                send_photo("This is a Mercury Vapor lamppost", TUTORIAL_URL + 'MV.png?raw=true', chat)
                send_photo("And finally, this is a Metal Halide lamppost", TUTORIAL_URL + 'MH.png?raw=true', chat)

            if 'Exit' in text:
                keyboard = build_keyboard(keyboard_menu)
                send_message('How can I help you?', chat, keyboard)

            if 'Finish' in text:
                del observations[user_id]
                send_message("See you soon! Say Hi whenever you want to send new observations.",chat)

            if 'Send a new observation of a different type than the previous one' in text:

                time_zone = observations[user_id]["time_zone"]
                
                if time_zone == "Day":
                    send_message("Awesome, you can take a photo now.",chat)
                else:
                    send_message("Awesome, place your grating in front of the camera and take a photo.",chat)

                
            if 'Send a new observation of the same type as the previous one' in text:

                send_observation(user_id, 0)
                keyboard = build_keyboard(keyboard_new)
                send_message("Your observation has been registered", chat)
                send_message("Do you want to send a new one?", chat, keyboard)


            if text == 'white' or text =='orange':

                observation = observations[user_id]
                observation["color"] = text
                observations[user_id] = observation
                send_observation(user_id, 0)
                keyboard = build_keyboard(keyboard_new)
                send_message("Your observation has been registered", chat)
                send_message("Do you want to send a new one?", chat, keyboard)

            if text == 'High Pressure Sodium' or text =='Low Pressure Sodium' or text =='Light-Emitting Diode Lamps' or text =='Metal Halide' or text =='Mercury Vapor' or text =='No spectra':

                observation = observations[user_id]

                classification = 0 #0 for normal, 1 for cassification

                if "classification" in observation:
                    del observation["classification"]
                    classification = 1

                observation["color"] = text               
                observations[user_id] = observation

                send_observation(user_id, classification)
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
                date = str(update["message"]["date"])
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

def upload_to_aws(local_file, bucket, s3_file):
    s3 = boto3.client('s3', aws_access_key_id=ACCESS_KEY,
                      aws_secret_access_key=SECRET_KEY)

    try:
        s3.upload_file(local_file, bucket, s3_file, ExtraArgs={"Metadata": {"Content-Type":"iage/jpeg"}, 'ACL':'public-read'})
        print("Upload Successful")
        return True
    except FileNotFoundError:
        print("The file was not found")
        return False
    except NoCredentialsError:
        print("Credentials not available")
        return False


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
