Tired of not being able to use your arduino mega as hid device? Want to be able to set up a lot of buttons for you controller, but dont want to be dealing with button matrixes?
Then this repo is for you. Compile the code, adjust vjoy and you are ready to go!
Warning! The code is for arduino mega! Dont brick you board trying to upload it onto different one!

Instructions(it's easy!):
1. Wire up all buttons properly to all digital pins on arduino (yes, up to 60 buttons and more then 120 wires, awfull!);
2. upload scetch to arduino mega 2560
3. add panel_bridge.py to autorun and start it
4. donload and configure vJoy. You must use first device with all buttons enabeled. Feel free to change it in the code if you need.
After you see red square in tray menu, you shoud be ready to go. Reconnect arduino. python file will create configuration file? where you can set physical pin to virtual button. You MAY be prompted to callibrate it, if so, just do what it says.
Done!

Now when you press physical button, arduino sends serial signal to your pc, which is being read by python script. Then script simply sends commands to vjoy, and you get these fancy 60 buttons to use.
Feel free to ask questions and  request any additional features!
