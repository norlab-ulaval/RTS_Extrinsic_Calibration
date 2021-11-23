import numpy as np
import random
import math
from numpy import linalg
import sys
import rosbag
from nav_msgs.msg import Odometry
from sensor_msgs.msg import Imu
from geometry_msgs.msg import Vector3Stamped
from sensor_msgs.msg import Imu
from std_msgs.msg import Float64MultiArray
from scipy.interpolate import interp1d
from matplotlib.patches import Ellipse
from scipy.spatial.transform import Rotation as R_scipy
from scipy.spatial.transform import Rotation as R
from scipy import interpolate
#from theodolite_node_msgs.msg import *
#from theodolite_node_msgs.msg import TheodoliteCoordsStamped
from std_msgs.msg import Header

class TheodoliteCoordsStamped:
	def __init__(self, header, theodolite_time, theodolite_id, status, azimuth, elevation, distance):
		self.header = header
		self.theodolite_time = theodolite_time
		self.theodolite_id = theodolite_id
		self.status = status
		self.azimuth = azimuth
		self.elevation = elevation
		self.distance = distance

###################################################################################################
###################################################################################################
# Read/write data from files

# Function to read a text file which contains the marker data for the calibration. The result given
# will be the different markers positions in one theodolite frame
# Input:
# - file_name: name of the file to read (the file should have the same structure than the usual one use by the raspi)
# - theodolite_reference_frame: number which indicates the frame where the markers positions will be
# Output: 
# - trimble_1: list of array markers points coordinates of the theodolite 1, in the frame chosen
# - trimble_2: list of array markers points coordinates of the theodolite 2, in the frame chosen
# - trimble_3: list of array markers points coordinates of the theodolite 3, in the frame chosen
# - T_.1: 4x4 rigid transform obtain according to the point-to-point minimization between the chosen frame and the theodolite 1 frame (Identity matrix if frame 1 chosen)
# - T_.2: 4x4 rigid transform obtain according to the point-to-point minimization between the chosen frame and the theodolite 2 frame (Identity matrix if frame 2 chosen)
# - T_.3: 4x4 rigid transform obtain according to the point-to-point minimization between the chosen frame and the theodolite 3 frame (Identity matrix if frame 3 chosen) 
def read_marker_file(file_name, theodolite_reference_frame):
	Points_t1_rasp = []
	Points_t2_rasp = []
	Points_t3_rasp = []
	T_I = np.identity(4)
	# Read text file
	file = open(file_name, "r")
	line = file.readline()
	line = file.readline()
	while line:
		item = line.split(",")
		if(int(item[0])==1 and int(item[2])==0):
			add_point(float(item[5]),float(item[4]),float(item[3]),Points_t1_rasp, 2)
		if(int(item[0])==2 and int(item[2])==0):
			add_point(float(item[5]),float(item[4]),float(item[3]),Points_t2_rasp, 2)
		if(int(item[0])==3 and int(item[2])==0):
			add_point(float(item[5]),float(item[4]),float(item[3]),Points_t3_rasp, 2)
		line = file.readline()
	file.close()

	Points_t1_rasp_arr = np.array(Points_t1_rasp).T
	Points_t2_rasp_arr = np.array(Points_t2_rasp).T
	Points_t3_rasp_arr = np.array(Points_t3_rasp).T
	trimble_1 = Points_t1_rasp_arr
	trimble_2 = Points_t2_rasp_arr
	trimble_3 = Points_t3_rasp_arr

	if(theodolite_reference_frame<=1):
		T_12_rasp = point_to_point_minimization(Points_t2_rasp_arr, Points_t1_rasp_arr)
		T_13_rasp = point_to_point_minimization(Points_t3_rasp_arr, Points_t1_rasp_arr)
		Points_t12_rasp = T_12_rasp@Points_t2_rasp_arr
		Points_t13_rasp = T_13_rasp@Points_t3_rasp_arr
		trimble_2 = Points_t12_rasp
		trimble_3 = Points_t13_rasp
		return trimble_1, trimble_2, trimble_3, T_I, T_12_rasp, T_13_rasp

	if(theodolite_reference_frame==2):
		T_21_rasp = point_to_point_minimization(Points_t1_rasp_arr, Points_t2_rasp_arr)
		T_23_rasp = point_to_point_minimization(Points_t3_rasp_arr, Points_t2_rasp_arr)
		Points_t21_rasp = T_21_rasp@Points_t1_rasp_arr
		Points_t23_rasp = T_23_rasp@Points_t3_rasp_arr
		trimble_1 = Points_t21_rasp
		trimble_3 = Points_t23_rasp
		return trimble_1, trimble_2, trimble_3, T_21_rasp, T_I, T_23_rasp

	if(theodolite_reference_frame>=3):
		T_31_rasp = point_to_point_minimization(Points_t1_rasp_arr, Points_t3_rasp_arr)
		T_32_rasp = point_to_point_minimization(Points_t2_rasp_arr, Points_t3_rasp_arr)
		Points_t31_rasp = T_31_rasp@Points_t1_rasp_arr
		Points_t32_rasp = T_32_rasp@Points_t2_rasp_arr
		trimble_1 = Points_t31_rasp
		trimble_2 = Points_t32_rasp
		return trimble_1, trimble_2, trimble_3, T_31_rasp, T_32_rasp, T_I

# Function which read a rosbag of theodolite data and return the trajectories found by each theodolite, and the timestamp of each point as a list
# Input:
# - file: name of the rosbag to open
# - Tf: list of rigid transform between each frame according to the chosen one, was found according to the markers positions. 
# Output: 
# - trajectory_trimble_1: list of 4x1 3D homogeneous coordinates for the theodolite 1
# - trajectory_trimble_2: list of 4x1 3D homogeneous coordinates for the theodolite 2
# - trajectory_trimble_3: list of 4x1 3D homogeneous coordinates for the theodolite 2
# - time_trimble_1: list of timestamp for each points for the theodolite 1, timestamp in double
# - time_trimble_2: list of timestamp for each points for the theodolite 2, timestamp in double
# - time_trimble_3: list of timestamp for each points for the theodolite 3, timestamp in double
def read_rosbag_theodolite_with_tf(file, Tf):
	bag = rosbag.Bag(file)
	trajectory_trimble_1=[]
	trajectory_trimble_2=[]
	trajectory_trimble_3=[]
	time_trimble_1 = []
	time_trimble_2 = []
	time_trimble_3 = []

	# Variable for counting number of data and number of mistakes
	it = np.array([0,0,0])
	bad_measures = 0
	#Read topic of trimble
	for _, msg, t in bag.read_messages(topics=['/theodolite_master/theodolite_data']):
		marker = TheodoliteCoordsStamped(msg.header, msg.theodolite_time, msg.theodolite_id, msg.status, msg.azimuth, msg.elevation, msg.distance)
		if(marker.status == 0): # If theodolite can see the prism, or no mistake in the measurement
			# Find number of theodolite
			if(marker.theodolite_id==1):
				add_point_in_frame(marker.distance, marker.azimuth, marker.elevation, trajectory_trimble_1, Tf[0], 2)
				time_trimble_1.append(second_nsecond(marker.header.stamp.secs, marker.header.stamp.nsecs))
				it[0]+=1
			if(marker.theodolite_id==2):
				add_point_in_frame(marker.distance, marker.azimuth, marker.elevation, trajectory_trimble_2, Tf[1], 2)
				time_trimble_2.append(second_nsecond(marker.header.stamp.secs, marker.header.stamp.nsecs))
				it[1]+=1
			if(marker.theodolite_id==3):
				add_point_in_frame(marker.distance, marker.azimuth, marker.elevation, trajectory_trimble_3, Tf[2], 2)
				time_trimble_3.append(second_nsecond(marker.header.stamp.secs, marker.header.stamp.nsecs))
				it[2]+=1
		# Count mistakes
		if(marker.status != 0):
			bad_measures+=1
	# Print number of data for each theodolite and the total number of mistakes
	print("Number of data for theodolites:", it)
	print("Bad measures:", bad_measures)

	return trajectory_trimble_1, trajectory_trimble_2, trajectory_trimble_3, time_trimble_1, time_trimble_2, time_trimble_3

# Function which read a rosbag of icp data and return the a list of the pose
# Input:
# - file: name of the rosbag to open
# Output: 
# - pose: list of 4x4 pose matrix
# - time_icp: list of timestamp for each pose
def read_rosbag_icp(filename):
	file = filename + ".bag"
	bag = rosbag.Bag(file)
	pose = []
	time_icp = []
	for _, msg, t in bag.read_messages(topics=['/icp_odom']):
		odom = Odometry(msg.header, msg.child_frame_id, msg.pose, msg.twist)
		time = second_nsecond(odom.header.stamp.secs, odom.header.stamp.nsecs)
		x=odom.pose.pose.position.x
		y=odom.pose.pose.position.y
		z=odom.pose.pose.position.z
		qx=odom.pose.pose.orientation.x
		qy=odom.pose.pose.orientation.y
		qz=odom.pose.pose.orientation.z
		qw=odom.pose.pose.orientation.w
		T = np.identity(4)
		r = R_scipy.from_quat([qx, qy, qz, qw])
		Rot_r = r.as_matrix()
		T[0:3,0:3]=Rot_r
		T[0,3] = x
		T[1,3] = y
		T[2,3] = z
		pose.append(T)
		time_icp.append(time)

	return pose, time_icp

# Function which convert interpolated data pose into a specific format to use evo library
# Input:
# - interpolated_time: list of timestamp of the pose
# - Pose_lidar: list of 4x4 matrix of the poses
# - output: name of the file to create
def grountruth_convert_for_eval(interpolated_time, Pose_lidar, output):
	groundtruth_file = open(output,"w+")
	iterator_lidar = 0
	for j in interpolated_time:
		for i in j:
			T = Pose_lidar[iterator_lidar]
			Rot = R_scipy.from_matrix(T[0:3,0:3])
			quat = Rot.as_quat()
			result = np.array([i, T[0,3], T[1,3], T[2,3], quat[0], quat[1], quat[2], quat[3]])
			groundtruth_file.write(str(result[0]))
			groundtruth_file.write(" ")
			groundtruth_file.write(str(result[1]))
			groundtruth_file.write(" ")
			groundtruth_file.write(str(result[2]))
			groundtruth_file.write(" ")
			groundtruth_file.write(str(result[3]))
			groundtruth_file.write(" ")
			groundtruth_file.write(str(result[4]))
			groundtruth_file.write(" ")
			groundtruth_file.write(str(result[5]))
			groundtruth_file.write(" ")
			groundtruth_file.write(str(result[6]))
			groundtruth_file.write(" ")
			groundtruth_file.write(str(result[7]))
			groundtruth_file.write("\n")
			iterator_lidar = iterator_lidar+1
	groundtruth_file.close()
	print("Conversion done !")

# Function which convert icp data pose into a specific format to use evo library
# Input:
# - time_icp: list of timestamp of the pose
# - Pose_lidar: list of 4x4 matrix of the poses
# - output: name of the file to create
def icp_convert_for_eval(time_icp, Pose_lidar, output):
	icp_file = open(output,"w+")
	iterator_lidar = 0
	for i in time_icp:
		T = Pose_lidar[iterator_lidar]
		Rot = R_scipy.from_matrix(T[0:3,0:3])
		quat = Rot.as_quat()
		result = np.array([i, T[0,3], T[1,3], T[2,3], quat[0], quat[1], quat[2], quat[3]])
		icp_file.write(str(result[0]))
		icp_file.write(" ")
		icp_file.write(str(result[1]))
		icp_file.write(" ")
		icp_file.write(str(result[2]))
		icp_file.write(" ")
		icp_file.write(str(result[3]))
		icp_file.write(" ")
		icp_file.write(str(result[4]))
		icp_file.write(" ")
		icp_file.write(str(result[5]))
		icp_file.write(" ")
		icp_file.write(str(result[6]))
		icp_file.write(" ")
		icp_file.write(str(result[7]))
		icp_file.write("\n")
		iterator_lidar = iterator_lidar+1
	icp_file.close()
	print("Conversion done !")

# Function which read a rosbag of odometry data and return the lists of the speed and acceleration data
# Input:
# - filename: name of the rosbag to open
# - wheel: option to select the topic to read (True:/warthog_velocity_controller/odom, False:/imu_and_wheel_odom)
# Output: 
# - speed: list of 1x2 matrix which contain the timestamp [0] and the speed [1] for each data
# - accel: list of 1x2 matrix which contain the timestamp [0] and the accel [1] for each data
def read_rosbag_imu_node(filename, wheel):
	bag = rosbag.Bag(filename)
	speed = []
	speed_only = []
	time_only = []
	accel = []
	if(wheel==True):
		topic_name = '/warthog_velocity_controller/odom'
	else:
		topic_name = '/imu_and_wheel_odom'
	for _, msg, t in bag.read_messages(topics=[topic_name]):
		odom = Odometry(msg.header, msg.child_frame_id, msg.pose, msg.twist)
		time = second_nsecond(odom.header.stamp.secs, odom.header.stamp.nsecs)
		vitesse_lineaire = odom.twist.twist.linear.x
		speed.append(np.array([time,vitesse_lineaire]))
		speed_only.append(vitesse_lineaire)
		time_only.append(time)
	speed_only_arr = np.array(speed_only)
	time_only_arr = np.array(time_only)
	diff_speed = np.diff(speed_only_arr)
	time_diff_mean = np.mean(np.diff(time_only_arr), axis=0)
	for i in range(0, len(diff_speed)):
		accel.append(np.array([time_only[i],diff_speed[i]/time_diff_mean]))
	return speed, accel

# Function which read a rosbag of imu data and return the list of the angular velocity around Z axis
# Input:
# - filename: name of the rosbag to open
# - wheel: option to select the topic to read (True:/imu_data, False:/MTI_imu/data)
# Output: 
# - speed: list of 1x2 matrix which contain the timestamp [0] and the angular velocity around Z axis [1] for each data
def read_rosbag_imu_data(filename, wheel):
	bag = rosbag.Bag(filename)
	speed = []
	if(wheel==True):
		topic_name = '/imu_data'
	else:
		topic_name = '/MTI_imu/data'
	for _, msg, t in bag.read_messages(topics=[topic_name]):
		imu = Imu(msg.header, msg.orientation, msg.orientation_covariance, msg.angular_velocity, msg.angular_velocity_covariance, msg.linear_acceleration, msg.linear_acceleration_covariance)
		time = second_nsecond(imu.header.stamp.secs, imu.header.stamp.nsecs)
		angular_velocity_z = imu.angular_velocity.z
		speed.append(np.array([time, angular_velocity_z]))
	return speed

# Function which read a rosbag of both GPS data and return the lists of the position data
# Input:
# - filename: name of the rosbag to open
# - number_gps: number of GPS to read (1 or less: front only, 2 or more: front and back)
# Output: 
# - gps_front: list of 1x4 array, [0]: timestamp, [1]: x position, [2]: y position, [3]: z position
# - gps_back: list of 1x4 array, [0]: timestamp, [1]: x position, [2]: y position, [3]: z position
def read_rosbag_gps_odom(filename, number_gps):
	bag = rosbag.Bag(filename)
	gps_front = []
	gps_back = []
	for _, msg, t in bag.read_messages(topics=['/odom_utm_front']):
		odom = Odometry(msg.header, msg.child_frame_id, msg.pose, msg.twist)
		time = second_nsecond(odom.header.stamp.secs, odom.header.stamp.nsecs)
		gps_position_x = odom.pose.pose.position.x
		gps_position_y = odom.pose.pose.position.y
		gps_position_z = odom.pose.pose.position.z
		gps_front.append(np.array([time, gps_position_x, gps_position_y, gps_position_z]))

	if(number_gps<=1):
		return gps_front
	else:
		for _, msg, t in bag.read_messages(topics=['/odom_utm_back']):
			odom = Odometry(msg.header, msg.child_frame_id, msg.pose, msg.twist)
			time = second_nsecond(odom.header.stamp.secs, odom.header.stamp.nsecs)
			gps_position_x = odom.pose.pose.position.x
			gps_position_y = odom.pose.pose.position.y
			gps_position_z = odom.pose.pose.position.z
			gps_back.append(np.array([time, gps_position_x, gps_position_y, gps_position_z]))
		return gps_front, gps_back

# Function which read the raw GPS file data and return the data read
# Print also the number of satellite seeing (mean, std, min, max)
# Input:
# - name_file: name of the rosbag to open
# - limit_compteur: number of line to skip to read at the begining of the file
# Output: 
# - GPS_front_raw_data: list of 1x4 array, [0]: timestamp, [1]: latitude (deg), [2]: longitude(deg), [3]: height (m)
def read_gps_file(name_file, limit_compteur):
	fichier = open(name_file, "r")
	compteur = 0
	GPS_front_raw_data = []
	satellite = []
	for line in fichier:
		if(compteur>limit_compteur):
			#print(line.split(" "))
			time = line.split(" ")[1]
			lat = line.split(" ")[4]
			long_i = line.split(" ")[6]
			height = line.split(" ")[10]
			time_split = time.split(":")
			#print(time_split)
			#print(lat, long_i, height)
			#print(height)
			time_sec = float(time_split[0].strip())*3600 + float(time_split[1].strip())*60 + float(time_split[2].strip())
			GPS_front_raw_data.append(np.array([time_sec, float(lat.strip()), float(long_i.strip()), float(height.strip())]))
			temporary_list=[]
			for i in line.split(" "):
				if(i!=''):
					temporary_list.append(i)
			#print(temporary_list)
			if(float(temporary_list[6])==2):
				print(compteur)
			satellite.append(float(temporary_list[6].strip()))
		compteur = compteur + 1
	fichier.close()
	print("Average satellite number:", round(np.mean(satellite),1), ", Std: ", round(np.std(satellite),1), ", Min :",  np.min(satellite),", Max :", np.max(satellite))
	return GPS_front_raw_data

# Function which convert the raw GPS data latitude and longitude to x,y in UTM frame
# Input:
# - Lat: latitude in deg
# - Long: longitude in deg
# Output: 
# - UTMEasting: corrected y position in UTM frame (m)
# - UTMNorthing: corrected x position in UTM frame (m)
def LLtoUTM(Lat, Long):
	RADIANS_PER_DEGREE = math.pi/180.0
	DEGREES_PER_RADIAN = 180.0/math.pi
	# WGS84 Parameters
	WGS84_A = 6378137.0;  
	WGS84_B = 6356752.31424518
	WGS84_F = 0.0033528107
	WGS84_E = 0.0818191908
	WGS84_EP = 0.0820944379
	# UTM Parameters
	UTM_K0 = 0.9996
	UTM_FE = 500000.0
	UTM_FN_N = 0.0
	UTM_FN_S = 10000000.0
	UTM_E2 = (WGS84_E*WGS84_E)
	UTM_E4 = (UTM_E2*UTM_E2)
	UTM_E6 = (UTM_E4*UTM_E2)
	UTM_EP2 = (UTM_E2/(1-UTM_E2))
	a = WGS84_A
	eccSquared = UTM_E2
	k0 = UTM_K0
	# Make sure the longitude is between -180.00 .. 179.9
	LongTemp = (Long+180)-int((Long+180)/360)*360-180
	LatRad = Lat*RADIANS_PER_DEGREE
	LongRad = LongTemp*RADIANS_PER_DEGREE
	ZoneNumber = int((LongTemp + 180)/6) + 1
	if( Lat >= 56.0 and Lat < 64.0 and LongTemp >= 3.0 and LongTemp < 12.0 ):
		ZoneNumber = 32
	# Special zones for Svalbard
	if( Lat >= 72.0 and Lat < 84.0 ):
		if(LongTemp >= 0.0  and LongTemp <  9.0 ):
			ZoneNumber = 31
		elif(LongTemp >= 9.0  and LongTemp < 21.0):
			ZoneNumber = 33
		elif(LongTemp >= 21.0 and LongTemp < 33.0):
			ZoneNumber = 35
		elif(LongTemp >= 33.0 and LongTemp < 42.0):
			ZoneNumber = 37
	# +3 puts origin in middle of zone
	LongOrigin = (ZoneNumber - 1)*6 - 180 + 3
	LongOriginRad = LongOrigin * RADIANS_PER_DEGREE
	# compute the UTM Zone from the latitude and longitude
	#snprintf(UTMZone, 4, "%d%c", ZoneNumber, UTMLetterDesignator(Lat))
	eccPrimeSquared = (eccSquared)/(1-eccSquared)
	N = a/math.sqrt(1-eccSquared * math.sin(LatRad) * math.sin(LatRad))
	T = math.tan(LatRad) * math.tan(LatRad)
	C = eccPrimeSquared * math.cos(LatRad) * math.cos(LatRad)
	A = math.cos(LatRad) * (LongRad-LongOriginRad)
	M = a*((1- eccSquared/4 - 3* eccSquared*eccSquared/64 - 5*eccSquared*eccSquared*eccSquared/256)*LatRad- (3*eccSquared/8	+ 3*eccSquared*eccSquared/32	+ 45*eccSquared*eccSquared*eccSquared/1024)*math.sin(2*LatRad)+ (15*eccSquared*eccSquared/256 + 45*eccSquared*eccSquared*eccSquared/1024)*math.sin(4*LatRad)- (35*eccSquared*eccSquared*eccSquared/3072)*math.sin(6*LatRad))
	UTMEasting = (k0*N*(A+(1-T+C)*A*A*A/6+ (5-18*T+T*T+72*C-58*eccPrimeSquared)*A*A*A*A*A/120)+ 500000.0)
	UTMNorthing = (k0*(M+N*math.tan(LatRad)*(A*A/2+(5-T+9*C+4*C*C)*A*A*A*A/24+ (61-58*T+T*T+600*C-330*eccPrimeSquared)*A*A*A*A*A*A/720)))
	if(Lat < 0):
		#10000000 meter offset for southern hemisphere
		UTMNorthing = UTMNorthing + 10000000.0 
	return UTMEasting, UTMNorthing

# Function which convert the raw GPS data to UTM frame for each data read
# Input:
# - GPS_front_raw_data: list of 1x4 array raw data of the GPS, [0]: timestamp, [1]: latitude (deg), [2]: longitude(deg), [3]: height (m)
# - limit_data: array of 1x2 to specifiy which data to read and convert ([0]: index of begining [1]: index of end)
# - time_origin: boolean to set the time origin to zero (True) or to let it compute with the hour, minute and second ot the day (False)
# Output: 
# - GPS_front_utm_data: list of 1x4 GPS data in UTM frame, [0]: timestamp, [1]: x(m), [2]: y(m), [3]: z(m)
def utm_gps_data(GPS_front_raw_data, limit_data, time_origin):
	GPS_front_utm_data = []
	compteur = 0
	origin_time = 0
	for i in GPS_front_raw_data:
		if(compteur == 0 and time_origin == True):
			origin_time = i[0]
		if(compteur >=limit_data[0] and compteur <= limit_data[1]):
			UTMEasting, UTMNorthing = LLtoUTM(i[1], i[2])	
			GPS_front_utm_data.append(np.array([i[0] - origin_time + limit_data[2], UTMNorthing, UTMEasting, i[3]]))
		compteur = compteur + 1
	return GPS_front_utm_data

# Function which convert the raw data to a csv file
# Input:
# - time_data: array 1xN of time for the data (in seconds)
# - point_data: array of 3xN of the trajectory to save
# - file_name: string for the path and file name of the csv file
def Convert_data_to_csv(time_data, point_data, file_name):
	csv_file = open(file_name, "w+")
	for i,j in zip(time_data, point_data):
		csv_file.write(str(i))
		csv_file.write(" ")
		csv_file.write(str(j[0]))
		csv_file.write(" ")
		csv_file.write(str(j[1]))
		csv_file.write(" ")
		csv_file.write(str(j[2]))
		csv_file.write("\n")
	csv_file.close()
	print("Conversion done !")

# Function which convert the inter-GPS distance to a csv file
# Input:
# - time_data: array 1xN of time for the data (in seconds)
# - distance: array of 1xN of the inter-GPS distance (m)
# - file_name: string for the path and file name of the csv file
def Convert_inter_distance_to_csv(time_data, distance, file_name):
	csv_file = open(file_name, "w+")
	for i,j in zip(time_data, distance):
		csv_file.write(str(i))
		csv_file.write(" ")
		csv_file.write(str(j))
		csv_file.write("\n")
	csv_file.close()
	print("Conversion done !")

# Function which reads data coming from a calibration file and put them in another file
# Input:
# - file_name: string for the path and file name of the csv file
def read_calibration_gps_prism(file_name, file_name_output):
	file = open(file_name, "r")
	line = file.readline()
	points_prism = []
	while line:
		item = line.split(" ")
		ha = float(item[0])+float(item[1])*1/60+float(item[2])*1/3600
		ha_sigma = float(item[3])+float(item[4])*1/60+float(item[5])*1/3600
		va = float(item[6]) + float(item[7]) * 1 / 60 + float(item[8]) * 1 / 3600
		va_sigma = float(item[9])+float(item[10])*1/60+float(item[11])*1/3600
		d = float(item[12])
		d_sigma = float(item[13])
		points_prism.append(give_points_without_correction(d, ha, va, 1))
		line = file.readline()
	file.close()

	dp12 = np.linalg.norm(points_prism[0]-points_prism[1], axis=0)
	dp13 = np.linalg.norm(points_prism[0] - points_prism[2], axis=0)
	dp23 = np.linalg.norm(points_prism[1] - points_prism[2], axis=0)
	dg12 = np.linalg.norm(points_prism[3] - points_prism[4], axis=0)
	dg13 = np.linalg.norm(points_prism[3] - points_prism[5], axis=0)
	dg23 = np.linalg.norm(points_prism[4] - points_prism[5], axis=0)

	print(dp12, dp13, dp23)
	print(dg12, dg13, dg23)

	csv_file = open(file_name_output, "w+")
	csv_file.write(str(dp12))
	csv_file.write(" ")
	csv_file.write(str(dp13))
	csv_file.write(" ")
	csv_file.write(str(dp23))
	csv_file.write(" ")
	csv_file.write(str(dg12))
	csv_file.write(" ")
	csv_file.write(str(dg13))
	csv_file.write(" ")
	csv_file.write(str(dg23))
	csv_file.write("\n")
	csv_file.close()

	print("Conversion done !")
###################################################################################################
###################################################################################################
# Process raw data from files

# Function to convert rosTime in seconds
# Input:
# - secs: Time seconds value
# - nsecs: Time nanoseconds value
# Output: seconds in double
def second_nsecond(secs, nsecs):
	#if(nsecs < )
	return secs+nsecs*10**(-9)

# Function to return a point according to the data of the theodolite as array
# Input:
# - d: distance in meter
# - ha: horizontale angle
# - va: verticale angle
# - param: 1 use angle in degrees, param: 2 use angle in radians
# Ouput: 4x1 array with the 3D coordinates according to the data
def give_points(d, ha, va, param):
	d = d + 0.01 # add 10mm because measurements done by raspi
	if(param ==1):
		x=d*math.cos((-ha)*np.pi/180)*math.cos((90-va)*np.pi/180)
		y=d*math.sin((-ha)*np.pi/180)*math.cos((90-va)*np.pi/180)
		z=d*math.sin((90-va)*np.pi/180)
	if(param ==2):
		x=d*math.cos(-ha)*math.cos(np.pi/2-va)
		y=d*math.sin(-ha)*math.cos(np.pi/2-va)
		z=d*math.sin(np.pi/2-va)
	return np.array([x, y, z, 1],dtype=np.float64)

def give_points_without_correction(d, ha, va, param):
	d = d + 0.01 # add 10mm because measurements done by raspi
	if(param ==1):
		x=d*math.cos((-ha)*np.pi/180)*math.cos((90-va)*np.pi/180)
		y=d*math.sin((-ha)*np.pi/180)*math.cos((90-va)*np.pi/180)
		z=d*math.sin((90-va)*np.pi/180)
	if(param ==2):
		x=d*math.cos(-ha)*math.cos(np.pi/2-va)
		y=d*math.sin(-ha)*math.cos(np.pi/2-va)
		z=d*math.sin(np.pi/2-va)
	return np.array([x, y, z, 1],dtype=np.float64)

# Function to convert a point according to the data of the theodolite into a frame according to a pose T,
# and put this point into a list of array
# Input:
# - d: distance in meter
# - ha: horizontale angle
# - va: verticale angle
# - points: list of points modified by the pose given
# - T: 4x4 pose matrix between the Frame of the point to the frame desired
# - param: 1 use angle in degrees, param: 2 use angle in radians
def add_point_in_frame(d, ha, va, points, T, param):
	vec = give_points(d, ha, va, param)
	vec_result = T@vec
	points.append(np.array([vec_result[0],vec_result[1],vec_result[2], 1],dtype=np.float64))

# Function to add a point in a list of array according to the data of the theodolite 
# Input:
# - d: distance in meter
# - ha: horizontale angle
# - va: verticale angle
# - points: list of points which the result point will be add
# - param: 1 use angle in degrees, param: 2 use angle in radians
def add_point(d, ha, va, points, param):
	points.append(give_points(d, ha, va, param))

###################################################################################################
###################################################################################################
# Theodolite function for processing

# Function which found the tf transform between two point clouds using point-to-point minimization, 
# where the matching was already done (mean each index of the point cloud for the reading and reference array match)
# Input:
# - P: the reading point cloud, can be 4xn or 3xn where n is the number of points
# - Q: the reference point cloud, can be 4xn or 3xn where n is the number of points
# Output: T a 4x4 pose matrix corresponding to the rigid transformation 
def point_to_point_minimization(P, Q):
	# Errors at the beginning
	errors_before = Q - P
	# Centroide of each pointcloud
	mu_p = np.mean(P[0:3,:],axis=1)
	mu_q = np.mean(Q[0:3,:], axis=1)
	# Center each pointcloud
	P_mu = np.ones((3, P.shape[1]))    
	Q_mu = np.ones((3, Q.shape[1])) 
	for i in range(0,P_mu.shape[1]):
		P_mu[0:3,i] = P[0:3,i] - mu_p
	for i in range(0,Q_mu.shape[1]):
		Q_mu[0:3,i] = Q[0:3,i] - mu_q
	# Compute cross covariance matrix
	H = P_mu@Q_mu.T
	# Use SVD decomposition
	U, s, V = np.linalg.svd(H)
	# Compute rotation
	R = V.T@U.T
	if(np.linalg.det(R)<0):
		#print(V.T)
		V_t = V.T
		V_t[:,2] = -V_t[:,2]
		R = V_t@U.T

	# Compute translation
	t = mu_q - R@mu_p
	# Compute rigid transformation obtained
	T = np.eye(4)
	T[0:3,0:3]=R
	T[0:3,3] = t
	return T

# Function to find prism not moving points according to the point just before in the array of the trajectories. 
# The not moving point are selected because of their position proximity
# Input:
# - trimble: list of trajectory points
# - limit_m: proximity limit in meters to find not moving points. If the distance between two near indexed points is less than the limit, 
# the point at the index i is selected
# Output: list of index of the not moving points
def find_not_moving_points(trimble, limit_m):
	ind_not_moving = []
	start_point = trimble[0:3,0]
	for i in range(1,len(trimble.T)):
		if(np.linalg.norm(trimble[0:3,i]-start_point)<limit_m):
			ind_not_moving.append(i)
		start_point = trimble[0:3,i] 
	return ind_not_moving

# Function to find lidar interpolated not moving points
# Input:
# - pose_lidar: list of lidar pose 4x4 matrix
# - limit_speed: threshold of the speed to consider a position as static (m/s)
# - time_inter: time between each interpolated points (s)
# Output: 
# - ind_not_moving: list of index of the not moving points
def find_not_moving_points_lidar(pose_lidar, limit_speed, time_inter):
	ind_not_moving = []
	for i in range(1,len(pose_lidar)):
		if(np.linalg.norm(pose_lidar[i,0:3,3]-pose_lidar[i-1,0:3,3])/time_inter<limit_speed):
			ind_not_moving.append(i)
	return ind_not_moving

# Function to find lidar interpolated moving points
# Input:
# - pose_lidar: list of lidar pose 4x4 matrix
# - limit_speed: threshold of the speed to consider a position as dynamic (m/s)
# - time_inter: time between each interpolated points (s)
# Output: 
# - ind_not_moving: list of index of the moving points
def find_moving_points_lidar(pose_lidar, limit_speed, time_inter):
	ind_not_moving = []
	for i in range(1,len(pose_lidar)):
		if(np.linalg.norm(pose_lidar[i,0:3,3]-pose_lidar[i-1,0:3,3])/time_inter>=limit_speed):
			speed = np.linalg.norm(pose_lidar[i,0:3,3]-pose_lidar[i-1,0:3,3])/time_inter
			ind_not_moving.append(np.array([i,speed]))
	return ind_not_moving

# Function to find cluster of not moving point
# Input:
# - trimble_time: list of time trajectory points
# - indice_trimble_list: list of index of not moving points in a trajectory
# - limit_time: proximity limit in second to find not moving points. If the time between two near indexed points is less than the limit, 
# these points are selected
# Output:
# - tuple_not_moving: list of array, each of this array contain the index of each cluster of not moving points in a trajectory
def find_cluster_not_moving_points(trimble_time, indice_trimble_list, limit_time):
	tuple_not_moving = []
	list_temporary = []
	start_cluster = 0
	for i in range(0,len(indice_trimble_list)-1):
		if(abs(trimble_time[indice_trimble_list[i+1]]-trimble_time[indice_trimble_list[i]])<=limit_time):
			list_temporary.append(indice_trimble_list[i])
		if((abs(trimble_time[indice_trimble_list[i+1]]-trimble_time[indice_trimble_list[i]])>limit_time or i==len(indice_trimble_list)-2) and len(list_temporary)>0):
			tuple_not_moving.append(np.array(list_temporary))
			if(len(list_temporary)<5):
				del tuple_not_moving[-1]
			list_temporary = []
	return tuple_not_moving

# Function to find cluster of interpolated lidar not moving point
# Input:
# - lidar_time: list of time trajectory points
# - indice_lidar_list: list of index of lidar not moving points in a trajectory
# - limit_time: proximity limit in second to find not moving points. If the time between two near indexed points is less than the limit, 
# these points are selected
# Output:
# - tuple_not_moving: list of array, each of this array contain the index of each cluster of not moving points in a trajectory
def find_cluster_not_moving_points_lidar(lidar_time, indice_lidar_list, limit_time):
	tuple_not_moving = []
	list_temporary = []
	start_cluster = 0
	for i in range(0,len(indice_lidar_list)-1):
		if(abs(lidar_time[indice_lidar_list[i+1]]-lidar_time[indice_lidar_list[i]])<=limit_time):
			list_temporary.append(indice_lidar_list[i])
		if(abs(lidar_time[indice_lidar_list[i+1]]-lidar_time[indice_lidar_list[i]])>limit_time or i==len(indice_lidar_list)-2):
			tuple_not_moving.append(np.array(list_temporary))
			list_temporary = []
	return tuple_not_moving

# Function to split a time array into several interval according to a limit between two timestamp
# Input:
# - time_trimble: list of time (s)
# - limit_time_interval: threshold which is used to split the time interval in two if the timestamp difference is too high
# Output:
# - list_time_interval: list of 1x2 array of the different index which defined each of the intervals, [0]: begin and [1]: end
def split_time_interval(time_trimble, limit_time_interval):
	list_time_interval = []
	begin = 0
	min_number_points = 2
	for i in range(1,len(time_trimble)):
		if(abs(time_trimble[i]-time_trimble[i-1])>limit_time_interval):
			if(i-begin>min_number_points):
				interval = np.array([begin, i-1])
				begin = i
				list_time_interval.append(interval)
			else:
				begin = i
		else:
			if(i == len(time_trimble)-1):
				interval = np.array([begin, i])
				begin = i
				list_time_interval.append(interval)
	return list_time_interval

# Function to find the closest index according to a timestamp in an simple list
# Input:
# - time_trimble: list of time (s)
# - time_interval: timestamp to find in the list (s)
# - limit_search: threshold of the time difference to use for the research (s)
# Output:
# - index: return the closest index found in the list, or -1 if there is not close index
def research_index_for_time(time_trimble, time_interval, limit_search):
	result = 0
	diff = limit_search
	index = 0
	found_one = 0
	for i in range(0,len(time_trimble)):
		if(abs(time_interval-time_trimble[i])< limit_search and diff > abs(time_interval-time_trimble[i])):
			diff = abs(time_interval-time_trimble[i])
			result = time_trimble[i]
			index = i
			found_one = 1
	if(found_one == 0):
		index = -1
	return index

# Function to find the closest index according to a timestamp in a list of 1x2 array
# Input:
# - speed: list of data, [0] timestamp
# - time_interval: timestamp to find in the list (s)
# - limit_search: threshold of the time difference to use for the research (s)
# Output:
# - index: return the closest index found in the list, or -1 if there is not close index
def research_index_for_time_speed(speed, time_interval, limit_search):
	result = 0
	diff = limit_search
	index = 0
	found_one = 0
	for i in range(0,len(speed)):
		if(abs(time_interval-speed[i][0])< limit_search and diff > abs(time_interval-speed[i][0])):
			diff = abs(time_interval-speed[i][0])
			result = speed[i][0]
			index = i
			found_one = 1
	if(found_one == 0):
		index = -1
	return index


# Returns element closest to target in an array
# Input:
# - arr: array of data 1xN, timestamp (s)
# - target: timestamp to find in arr (s)
# Output:
# - index: return the closest index found in arr and the value
def findClosest(arr, target):
	n = len(arr)
	# Corner cases
	if (target <= arr[0]):
		return 0, arr[0]
	if (target >= arr[n - 1]):
		return n - 1, arr[n - 1]

	# Doing binary search
	i = 0;
	j = n;
	mid = 0
	while (i < j):
		mid = (i + j) // 2
		if (arr[mid] == target):
			return mid, arr[mid]
		# If target is less than array
		# element, then search in left
		if (target < arr[mid]):
			# If target is greater than previous
			# to mid, return closest of two
			if (mid > 0 and target > arr[mid - 1]):
				return mid, getClosest(arr[mid - 1], arr[mid], target)
			# Repeat for left half
			j = mid
		# If target is greater than mid
		else:
			if (mid < n - 1 and target < arr[mid + 1]):
				return mid, getClosest(arr[mid], arr[mid + 1], target)
			# update i
			i = mid + 1
	# Only single element left after search
	return mid, arr[mid]

# Method to compare which one is the more close.
# We find the closest by taking the difference
# between the target and both values. It assumes
# that val2 is greater than val1 and target lies
# between these two.
def getClosest(val1, val2, target):
	if (target - val1 >= val2 - target):
		return val2
	else:
		return val1

# Function to compute the cluster of not moving points from the prisms according to the spacial and time distance
# Input:
# - trimble_1, trimble_2, trimble_3: list of prism positions for each theodolite
# - time_trimble_1, time_trimble_2, time_trimble_3: list of time for each prism position
# - dist_max: distance max for a prism to be part of a cluster
# - time_max: time max for a prism to be part of a cluster
# Output:
# - tuple_not_moving_trimble_1, tuple_not_moving_trimble_2, tuple_not_moving_trimble_3: list of index cluster for not moving points
def cluster_not_moving_points(trimble_1, trimble_2, trimble_3, time_trimble_1, time_trimble_2, time_trimble_3, dist_max, time_max):
	# find cluster by distance
	not_moving_trimble_1 = find_not_moving_points(trimble_1, dist_max)
	not_moving_trimble_2 = find_not_moving_points(trimble_2, dist_max)
	not_moving_trimble_3 = find_not_moving_points(trimble_3, dist_max)
	# sort these cluster with the time
	tuple_not_moving_trimble_1 = find_cluster_not_moving_points(time_trimble_1, not_moving_trimble_1, time_max)
	tuple_not_moving_trimble_2 = find_cluster_not_moving_points(time_trimble_2, not_moving_trimble_2, time_max)
	tuple_not_moving_trimble_3 = find_cluster_not_moving_points(time_trimble_3, not_moving_trimble_3, time_max)
	return tuple_not_moving_trimble_1, tuple_not_moving_trimble_2, tuple_not_moving_trimble_3

# Function to compute the distance between prisms for the not moving points cluster
# Input:
# - interpolated_trajectories: list of the different interpolated trajectories
# - tuple_not_moving_lidar: list the index of the tuple not moving points
# Output:
# - distance_error_12, distance_error_13, distance_error_23: list of index cluster for not moving points
def not_moving_interpolated_points(interpolated_trajectories, tuple_not_moving_lidar):
	interpolated_prism_pose = []
	# concatenate all the sub-trajectories in one for each prism
	interpolated_prism_pose = interpolated_trajectories[0]
	for i in range(1,len(interpolated_trajectories)):
		interpolated_prism_pose[0] = np.concatenate((interpolated_prism_pose[0],interpolated_trajectories[i][0]), axis=1)
		interpolated_prism_pose[1] = np.concatenate((interpolated_prism_pose[1],interpolated_trajectories[i][1]), axis=1)
		interpolated_prism_pose[2] = np.concatenate((interpolated_prism_pose[2],interpolated_trajectories[i][2]), axis=1)
	# With the cluster index, find the mean of the prism position for each of the cluster
	mean_not_moving_trimble_1 = []
	mean_not_moving_trimble_2 = []
	mean_not_moving_trimble_3 = []
	for i in tuple_not_moving_lidar:
		mean_not_moving_trimble_1.append(np.mean(interpolated_prism_pose[0][:,i],axis=1))
		mean_not_moving_trimble_2.append(np.mean(interpolated_prism_pose[1][:,i],axis=1))
		mean_not_moving_trimble_3.append(np.mean(interpolated_prism_pose[2][:,i],axis=1))
	# calculate the inter-prism distance for each of the cluster
	distance_error_12 = []
	distance_error_13 = []
	distance_error_23 = []
	for i,j,k in zip(mean_not_moving_trimble_1,mean_not_moving_trimble_2,mean_not_moving_trimble_3):
		distance_error_12.append(abs(np.linalg.norm(i-j)-np.linalg.norm(Prism_1-Prism_2))*1000)
		distance_error_13.append(abs(np.linalg.norm(k-j)-np.linalg.norm(Prism_3-Prism_2))*1000)
		distance_error_23.append(abs(np.linalg.norm(i-k)-np.linalg.norm(Prism_1-Prism_3))*1000)
	return distance_error_12, distance_error_13, distance_error_23

###################################################################################################
###################################################################################################
# Function for plot

# Function to find the eigenvectors and eigenvalues of a covariance matrix
# Input: covariance matrix
# Output:
# - vals: eigenvalues
# - vecs: eigenvectors
def eigsorted(cov):
	vals, vecs = np.linalg.eigh(cov)
	order = vals.argsort()[::-1]
	return vals[order], vecs[:,order]

# Function to find the parameter to plot on ellipse in 2D
# Input:
# - cov: covariance matrix of the point cloud
# Output:
# - width: width of the ellipse
# - height: height of the ellipse
# - theta: angle between the two eigenvectors
def cov_ellipse(cov):
	vals, vecs = eigsorted(cov)
	theta = np.degrees(np.arctan2(*vecs[:, 0][::-1]))
	# Width and height are "full" widths, not radius
	width, height = np.sqrt(vals)
	return width, height, theta

# Function to interpolate a 3D position trajectory
# Input:
# - row: list of position
# - res: number of interpolation for all the trajectory
# - method: method use for the interpolation
# Output:
# - arr: arr of 1x3 with the 3D position
def sample3DCurves(row, res=10, method='linear'):
	# edit: cleaner algebra
	x, *y, z = row
	# vecs between subsequently measured points
	vecs = np.diff(row)
	# path: cum distance along points (norm from first to ith point)
	path = np.cumsum(np.linalg.norm(vecs, axis=0))
	path = np.insert(path, 0, 0)
	## coords of interpolation
	coords = np.linspace(path[0], path[-1], res) #p[0]=0 p[-1]=max(p)
	# interpolation func for each axis with the path
	sampleX = interpolate.interp1d(path, row[0], kind=method)
	sampleY = interpolate.interp1d(path, row[1], kind=method)
	sampleZ = interpolate.interp1d(path, row[2], kind=method)
	# sample each dim
	xnew = sampleX(coords)
	ynew = sampleY(coords)
	znew = sampleZ(coords)
	arr = np.array([xnew, ynew, znew])
	return arr

# Function to compute the density function of a Gaussian
# Input:
# - x: array of x axis data
# - mean: mean of the Gaussian function
# - sd: standard deviation of the Gaussian function
# Output:
# - prob_density: array with value of the Gaussian function according to the x array
def normal_dist(x , mean , sd):
	prob_density = (1/(2*np.pi*sd**2) ) * np.exp(-0.5*((x-mean)/sd)**2)
	return prob_density

###################################################################################################
###################################################################################################
# Function for GPS data processing

# Function to find the GPS data according to a timestamp given
# Input:
# - gps_list: list of GPS position, array of 1x4, [0] timestamp
# - index_list: list of index of the GPS list to test
# - time_interval: timestamp given (s)
# - limit_search: threshold for the time research (s)
# Output:
# - index: index corresponding to the closest timestamp found, -1 if no one found
def research_index_for_time_gps(gps_list, index_list, time_interval, limit_search):
	result = 0
	diff = limit_search
	index = 0
	found_one = 0
	for i in index_list:
		if(abs(time_interval-gps_list[i][0])< limit_search and diff > abs(time_interval-gps_list[i][0])):
			diff = abs(time_interval-gps_list[i][0])
			result = gps_list[i][0]
			index = i
			found_one = 1
	if(found_one == 0):
		index = -1
	return index

# Function to compute the speed of the GPS (m/s)
# Input:
# - GPS_front_utm_data: list of GPS position, array of 1x4, [0] timestamp, [1] x(m), [2] y(m), [3] z(m)
# Output:
# - linear_speed_gps_utm: list of the GPS speed
def speed_gps(GPS_front_utm_data):
	linear_speed_gps_utm = []
	for i in range(0, len(GPS_front_utm_data)):
		if(i<len(GPS_front_utm_data)-1):
			data_i = GPS_front_utm_data[i]
			data_i2 = GPS_front_utm_data[i+1]
			distance = np.linalg.norm(np.array([data_i2[1],data_i2[2],data_i2[3]])-np.array([data_i[1],data_i[2],data_i[3]]))
			time_diff = data_i2[0]-data_i[0]
			speed = distance/time_diff
			if(speed<10):
				linear_speed_gps_utm.append(np.array([data_i[0],distance/time_diff]))
	return linear_speed_gps_utm




