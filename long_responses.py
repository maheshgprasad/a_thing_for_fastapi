import random

R_EATING = "I don't like eating anything because I'm a bot obviously!"
R_SOUND = "beep boop beep boop"
R_WEATHER = "Cloudy with a chance of meatballs, He he"
R_ME = "Hi, I am Mi-Joo Your Personal Assistant, Annyeonghaseyo!"

def unknown():
    response= ['Could you please re-phrase that?',
               "...",
               "Sounds about right",
               "What does that mean?"               
               ][random.randrange(4)]
    return response