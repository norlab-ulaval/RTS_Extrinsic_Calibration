import numpy as np

# Old value of prism
Prism_1_old = np.array([-0.11493461, -0.32969205, 0.33997508])
Prism_2_old = np.array([-1.04115493, 0.00147775, 0.23972586])
Prism_3_old = np.array([-0.29393989, 0.32581738, 0.28939597])

Prism_1 = np.array([-0.12413052, -0.32998385, 0.34745009])
Prism_2 = np.array([-1.05061716, -0.00439399, 0.2448696])
Prism_3 = np.array([-0.30736107, 0.32429536, 0.30031949])
Dist_prism_12 = np.linalg.norm(Prism_1-Prism_2)*1000
Dist_prism_13 = np.linalg.norm(Prism_1-Prism_3)*1000
Dist_prism_23 = np.linalg.norm(Prism_2-Prism_3)*1000

### Protocol not validated ###

# 01 11 2021
Dist_prism_12_011121 = 1.0398341231585624
Dist_prism_13_011121 = 0.818424700118086
Dist_prism_23_011121 = 0.8806156053859284
Dist_GPS_12_011121 = 0.835637436093363
Dist_GPS_13_011121 = 0.7812173648662254
Dist_GPS_23_011121 = 0.5166745729506486

# 26 11 2021
Dist_prism_12_261121 = 1.03688797895733
Dist_prism_13_261121 = 0.822536135483593
Dist_prism_23_261121 = 0.8783765747673403
Dist_GPS_12_261121 = 0.7828618536473139
Dist_GPS_13_261121 = 0.8394208131018045
Dist_GPS_23_261121 = 0.5176447366930409

# 31 01 2022
Dist_prism_12_310122 = 1.038854051807371
Dist_prism_13_310122 = 0.8202157646292075
Dist_prism_23_310122 = 0.879788333022114
Dist_GPS_12_310122 = 0.7830826912858335
Dist_GPS_13_310122 = 0.8418404054627937
Dist_GPS_23_310122 = 0.5172558618541933

# 03 02 2022
Dist_prism_12_030222 = 1.0403741344089559
Dist_prism_13_030222 = 0.8239475424257701
Dist_prism_23_030222 = 0.8766711748547112
Dist_GPS_12_030222 = 0.781661929058067
Dist_GPS_13_030222 = 0.8353981332464246
Dist_GPS_23_030222 = 0.5174987476948135

### Protocol validated ###

# 17 02 2022
Dist_prism_12_170222 = 1.0377436460567973
Dist_prism_13_170222 = 0.8262903370535766
Dist_prism_23_170222 = 0.8882613537922258
Dist_GPS_12_170222 = 0.7809786915630756
Dist_GPS_13_170222 = 0.8378323585433202
Dist_GPS_23_170222 = 0.5191788936274444

# 24 02 2022
Dist_prism_12_240222 = 1.0377436460567973
Dist_prism_13_240222 = 0.8262903370535766
Dist_prism_23_240222 = 0.8882613537922258
Dist_GPS_12_240222 = 0.7809786915630756
Dist_GPS_13_240222 = 0.8378323585433202
Dist_GPS_23_240222 = 0.5191788936274444

# 07 03 2022
Dist_prism_12_070322 = 0.8832836583456264
Dist_prism_13_070322 = 0.8247449387008166
Dist_prism_23_070322 = 1.039409793600046
Dist_GPS_12_070322 = 0.7781099344563802
Dist_GPS_13_070322 = 0.8431026980109139
Dist_GPS_23_070322 = 0.5157221841320069

# 12 03 2022
Dist_prism_12_120322 = 0.8860734460339026
Dist_prism_13_120322 = 0.8303896290142598
Dist_prism_23_120322 = 1.0393117663247973
Dist_GPS_12_120322 = 0.7829424296161074
Dist_GPS_13_120322 = 0.8415176433032493
Dist_GPS_23_120322 = 0.5161917038941966

# 14 03 2022 / 16 03 2022
Dist_prism_12_140322 = 0.8873171656784946
Dist_prism_13_140322 = 0.8272212117473343
Dist_prism_23_140322 = 1.0379270641796363
Dist_GPS_12_140322 = 0.7829081036179948
Dist_GPS_13_140322 = 0.8424633975958637
Dist_GPS_23_140322 = 0.5165807364575292

# 31 03 2022
Dist_prism_12_310322 = 0.8873171656784946
Dist_prism_13_310322 = 0.8272212117473343
Dist_prism_23_310322 = 1.0379270641796363
Dist_GPS_12_310322 = 0.7829081036179948
Dist_GPS_13_310322 = 0.8424633975958637
Dist_GPS_23_310322 = 0.5165807364575292

# 27 04 2022
Dist_prism_12_270422_1 = 0.8856608085851714
Dist_prism_13_270422_1 = 0.8264452483880412
Dist_prism_23_270422_1 = 1.0384219210289538
Dist_GPS_12_270422_1 = 0.7809547832390561
Dist_GPS_13_270422_1 = 0.8259590286006459
Dist_GPS_23_270422_1 = 0.5191274645630007

# 27 04 2022 evening
Dist_prism_12_270422_2 = 0.8868846942534616
Dist_prism_13_270422_2 = 0.829169129877633
Dist_prism_23_270422_2 = 1.0387571594276301
Dist_GPS_12_270422_2 = 0.7837749633840095
Dist_GPS_13_270422_2 = 0.8323125081688734
Dist_GPS_23_270422_2 = 0.5187055120945835

# 05 05 2022
Dist_prism_12_050522 = 0.3819811991689936
Dist_prism_13_050522 = 0.4426382054042266
Dist_prism_23_050522 = 0.2564685508415531

# 13 05 2022
Dist_prism_12_130522 = 0.8113569618671205
Dist_prism_13_130522 = 0.8695313906832193
Dist_prism_23_130522 = 1.0383292631343506
Dist_GPS_12_130522 = 0.7800801192552722
Dist_GPS_13_130522 = 0.8396027021467387
Dist_GPS_23_130522 = 0.5157656903777014

# 23 05 2022
Dist_prism_12_230522 = 0.3851913749758221
Dist_prism_13_230522 = 0.4433899497583272
Dist_prism_23_230522 = 0.25861327466684897

# 25 05 2022
Dist_prism_12_250522 = 0.9095421527752512
Dist_prism_13_250522 = 0.7356677023921305
Dist_prism_23_250522 = 1.0283049452358466

# 22 06 2022
Dist_prism_12_220622 = 0.7359204697527427
Dist_prism_13_220622 = 0.9055056357941131
Dist_prism_23_220622 = 1.0268390664025775
Dist_GPS_12_220622 = 0.7818105926683322
Dist_GPS_13_220622 = 0.8536205673813737
Dist_GPS_23_220622 = 0.5068640574720596

# 30 06 2022
Dist_prism_12_300622 = 0.7297583705742492
Dist_prism_13_300622 = 0.9060320633355149
Dist_prism_23_300622 = 1.0319114860615324
Dist_GPS_12_300622 = 0.7844037235850999
Dist_GPS_13_300622 = 0.8443517677165984
Dist_GPS_23_300622 = 0.515075228247105

# 11 07 2022
Dist_prism_12_110722 = 0.7290056530579362
Dist_prism_13_110722 = 0.906995998154099
Dist_prism_23_110722 = 1.029264651249632
Dist_GPS_12_110722 = 0.7825177240721779
Dist_GPS_13_110722 = 0.8446820009426457
Dist_GPS_23_110722 = 0.5145776023584968
