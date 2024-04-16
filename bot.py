import os
import telebot
from telebot import types
import stripe
import subprocess
import requests
import json
import logging
import telebot
import requests
import time
import phonenumbers
from twilio.rest import Client

from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

API_TOKEN = os.getenv('API_TOKEN')
STRIPE_API_KEY = os.getenv('STRIPE_API_KEY')
FLASK_WRAPPER_URL = os.getenv('FLASK_WRAPPER_URL')
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_PHONE_NUMBER = os.getenv('TWILIO_PHONE_NUMBER')

bot = telebot.TeleBot(API_TOKEN)
stripe.api_key = STRIPE_API_KEY

# comfyUI prompt endpoint
PROMPT_URL = os.getenv('PROMPT_URL')
COMFY_OUTPUT_DIR = os.getenv('COMFY_OUTPUT_DIR')

# start command
@bot.message_handler(commands=['start'])
def send_welcome(message):
    welcome_text = ("Welcome to Mira AI!\n\n"
                    "You can chat, receive audio messages, call, and get 🔥 pics from Mira.\n\n"
                    "Use /image to generate an image, use /call to call Mira, and use /subscribe to start chatting with Mira\n\n"
                    "Say “Hey” to get started!")
    bot.reply_to(message, welcome_text)

@bot.message_handler(commands=['payments', 'deposit'])
def handle_payments(message):
    # Define your Stripe product IDs here
    product_ids = {
        '2': 'price_1OnRPkSDPH8n3uDEY2gZGOIi',
        '8': 'price_1OnRQkSDPH8n3uDEpzONyfCp',
        '20': 'price_1OnRR7SDPH8n3uDEiKuLkrvu',
        '50': 'price_1OnRSASDPH8n3uDES16z8diB',
        '100': 'price_1OnRSXSDPH8n3uDETO89ZHhw',
        '200': 'price_1OnRSxSDPH8n3uDEdWQi43oq',
    }

    markup = types.InlineKeyboardMarkup(row_width=3)
    buttons = []

    for label, price_id in product_ids.items():
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{'price': price_id, 'quantity': 1}],
            mode='payment',
            success_url='https://your-success-url.com/',
            cancel_url='https://your-cancel-url.com/',
        )
        button = types.InlineKeyboardButton(f'{label} Credits', url=session.url)
        buttons.append(button)

    # Split buttons into rows of 3
    while buttons:
        markup.add(*buttons[:3])
        buttons = buttons[3:]

    # Send the message with multiple payment options
    bot.send_message(
        message.chat.id,
        "Add credits to generate images and phone calls! 😉😈\n\n"
        "Payments are securely powered. Please select a deposit amount:\n\n"
        "(1 SFW Image = 1 Credit, 1 NSFW = 2 Credits)\n"
        "1 min = 1 Credit (☎️)",
        reply_markup=markup
    )

# image command
@bot.message_handler(commands=['image'])
def request_image_prompt(message):

    markup = types.InlineKeyboardMarkup(row_width=2)  # Set row_width to 2 for two buttons
    sfw_button = types.InlineKeyboardButton("SFW 🔥", callback_data='sfw')
    nsfw_button = types.InlineKeyboardButton("NSFW 💦", callback_data='nsfw')

    markup.add(sfw_button, nsfw_button)

    # Send the message with the buttons
    bot.send_message(
        message.chat.id,
        "Choose between options: Safe for Work (SFW 🔥) or Not Safe for Work (NSFW 💦) Images.",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: True)
def handle_callback_query(call):
    if call.data == 'sfw':
        bot.send_message(call.message.chat.id, "Please enter some prompt for Safe for Work (SFW) image:")
        bot.register_next_step_handler(call.message, process_prompt, 'sfw')
    elif call.data == 'nsfw':
        bot.send_message(call.message.chat.id, "Please enter some prompt for Not Safe for Work (NSFW) image:")
        bot.register_next_step_handler(call.message, process_prompt, 'nsfw')

def process_prompt(message, option):
    prompt = message.text
    bot.send_message(message.chat.id, "Okay give me a little while to generate this ❤️")

    # Store user ID along with prompt
    user_prompt_data[message.chat.id] = {"prompt": prompt, "option": option}

    image_path = generate_image(message.chat.id)
    print("Image requested by" + message.chat.id)

    if image_path:
        try:
            with open(image_path, 'rb') as image_file:
                bot.send_photo(message.chat.id, photo=image_file)
        except FileNotFoundError:
            bot.send_message(message.chat.id, "Couldn't find image")
        except Exception as e:
            bot.send_message(message.chat.id, f"An error occurred: {str(e)}")
    else:
        bot.send_message(message.chat.id, "Sorry, I couldn't generate an image right now.")

# Dictionary to store user prompt data
user_prompt_data = {}

# generate image using workflow
def generate_image(user_id):
    user_data = user_prompt_data.get(user_id)
    if not user_data:
        return None

    print(user_id)
    print(user_data)

    prompt = user_data["prompt"]
    option = user_data["option"] # this option later will be use to check image type [sfw, nsfw]

    with open("utils/workflow.json", "r") as workflow_config:
        workflow_prompt = json.load(workflow_config)

    # Generate a unique seed for each image generation
    unique_seed = int(time.time() * 1000) # Using current timestamp in milliseconds

    # Modify the workflow_prompt to include the unique_seed
    workflow_prompt['4']['inputs']['seed'] = unique_seed

    # Filter prompt
    final_prompt = "tanned woman " + prompt

    # Add custom user prompt
    workflow_prompt['2']['inputs']['text'] = final_prompt

    # Check for any previously generated image
    prev_image = get_latest_image(COMFY_OUTPUT_DIR)

    start_queue(workflow_prompt)

    while True:
        latest_image = get_latest_image(COMFY_OUTPUT_DIR)
        if latest_image != prev_image:
            # Remove user data after image is generated
            del user_prompt_data[user_id]
            return latest_image
        time.sleep(1)

# get latest image
def get_latest_image(folder):
    files = os.listdir(folder)
    image_files = [f for f in files if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
    image_files.sort(key=lambda x: os.path.getmtime(os.path.join(folder, x)))
    latest_image = os.path.join(folder, image_files[-1] if image_files else None)
    return latest_image

# start queue
def start_queue(prompt_workflow):
    p = {"prompt": prompt_workflow}
    queue_data = json.dumps(p).encode('utf-8')
    requests.post(PROMPT_URL, data=queue_data)
#call feature

@bot.message_handler(commands=['call'])
def request_phone_number(message):
    msg = bot.reply_to(message, "Please type your phone number to initiate the call.")
    bot.register_next_step_handler(msg, process_phone_number)

def process_phone_number(message):
    phone_number = message.text
    try:
        # Parse the phone number
        parsed_number = phonenumbers.parse(phone_number, None)
        # Check if the number is valid
        if phonenumbers.is_valid_number(parsed_number):
            # Format the number to E.164 format which is required by Twilio
            formatted_number = phonenumbers.format_number(parsed_number, phonenumbers.PhoneNumberFormat.E164)
            initiate_call(formatted_number)
            bot.send_message(message.chat.id, "Call initiated! Please check your phone.")
        else:
            raise ValueError("Invalid phone number.")
    except (phonenumbers.phonenumberutil.NumberParseException, ValueError):
        msg = bot.reply_to(message, "Invalid phone number. Please enter a valid phone number, including country code.")
        bot.register_next_step_handler(msg, process_phone_number)

#Update TwiML to Stream Audio to WebSocket
def initiate_call(to_number):
    client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    call = client.calls.create(
        twiml=f'''
<Response>
  <Start>
    <Stream url="wss://https://02bd-223-178-209-185.ngrok-free.app /"/>
    </Start>
    <Say>Please start speaking, and your speech will be transcribed.</Say>
    <Pause length="60"/>
</Response>
''',
        to=to_number,
        from_=TWILIO_PHONE_NUMBER
    )
    print(f"Call initiated! Call SID: {call.sid}")

#chat

chat_sessions = {}

@bot.message_handler(commands=['chat'])
def start_chat(message):
    chat_id = message.chat.id
    chat_sessions[chat_id] = {"active": True, "history": []}  # Initialize chat session
    bot.send_message(chat_id, "Chat mode activated! Start chatting with Mira. Use /endchat to exit chat mode.")

@bot.message_handler(commands=['endchat'])
def end_chat(message):
    chat_id = message.chat.id
    if chat_id in chat_sessions:
        del chat_sessions[chat_id]  # End the chat session
    bot.send_message(chat_id, "Chat mode deactivated.")

@bot.message_handler(func=lambda message: message.chat.id in chat_sessions and chat_sessions[message.chat.id]['active'])
def process_chat_message(message):
    chat_id = message.chat.id
    input_text = message.text
    generate_chat_response(input_text, chat_id)

def generate_chat_response(input_text, chat_id):
    history = chat_sessions[chat_id]['history']
    history.append({"role": "user", "content": input_text})

    data = {
        "messages": history,
        "mode": "chat",
        "character": "Mira_A_horny_and_flirty_twitch_streamer"
    }

    headers = {"Content-Type": "application/json"}
    try:
        response = requests.post(
            "https://awesome-sellers-unwrap-screensaver.trycloudflare.com/v1/chat/completions",
            headers=headers,
            json=data,
            timeout=None  # No timeout
        )

        if response.status_code == 200:
            try:
                assistant_message = response.json()['choices'][0]['message']['content']
                if assistant_message:
                    bot.send_message(chat_id, assistant_message)
                    history.append({"role": "assistant", "content": assistant_message})
                else:
                    bot.send_message(chat_id, "Still generating the response, please wait...")
            except KeyError:
                bot.send_message(chat_id, "Response format is unexpected, please check the API.")
        else:
            bot.send_message(chat_id, f"Error with API: {response.status_code} {response.text}")

    except requests.exceptions.RequestException as e:
        bot.send_message(chat_id, "An error occurred: " + str(e))

@bot.message_handler(func=lambda message: True)  # This handler will catch all other messages
def handle_other_commands(message):
    chat_id = message.chat.id
    if chat_id in chat_sessions:
        if not chat_sessions[chat_id]['active']:
            bot.reply_to(message, "You're not currently in chat mode. Use /chat to start chatting!")
        else:
            process_chat_message(message)
    else:
        bot.reply_to(message, "Send /chat to start chatting or use other commands!")


if __name__ == '__main__':
    print("""
░█████╗░░█████╗░██████╗░████████╗███████╗██╗░░██╗██╗░█████╗░░░░██╗░░░░░░█████╗░██████╗░░██████╗
██╔══██╗██╔══██╗██╔══██╗╚══██╔══╝██╔════╝╚██╗██╔╝██║██╔══██╗░░░██║░░░░░██╔══██╗██╔══██╗██╔════╝
██║░░╚═╝██║░░██║██████╔╝░░░██║░░░█████╗░░░╚███╔╝░██║███████║░░░██║░░░░░███████║██████╦╝╚█████╗░
██║░░██╗██║░░██║██╔══██╗░░░██║░░░██╔══╝░░░██╔██╗░██║██╔══██║░░░██║░░░░░██╔══██║██╔══██╗░╚═══██╗
╚█████╔╝╚█████╔╝██║░░██║░░░██║░░░███████╗██╔╝╚██╗██║██║░░██║██╗███████╗██║░░██║██████╦╝██████╔╝
░╚════╝░░╚════╝░╚═╝░░╚═╝░░░╚═╝░░░╚══════╝╚═╝░░╚═╝╚═╝╚═╝░░╚═╝╚═╝╚══════╝╚═╝░░╚═╝╚═════╝░╚═════╝░

Mira Bot started...""")
    bot.infinity_polling()

