#!/usr/bin/python
# coding=utf-8

import os
import math
import pickle
import smbus
import struct
from random import randrange

bus = smbus.SMBus(0)
oled_addr = 0x3C

def oled_send(command_bytes, mode='command'):
	control_byte = 0b11000000 if mode == 'ram_data' else 0b10000000
	last_control_byte = control_byte & 0b01111111
	first_control_byte = control_byte if len(command_bytes) > 1 else last_control_byte
	bytes_to_send = []
	for i,byte in enumerate(command_bytes):
		if (i > 0):
			bytes_to_send.append(control_byte if i<len(command_bytes)-1 else last_control_byte)
		bytes_to_send.append(byte)
	bus.write_i2c_block_data(oled_addr, first_control_byte, bytes_to_send)

def oled_send_ram_data(data_bytes):
	n = 16
	chunks = [data_bytes[i * n:(i + 1) * n] for i in range((len(data_bytes) + n - 1) // n )]
	for chunk in chunks:
		oled_send(chunk, 'ram_data')

def enable_display():
	oled_send([0xAF])

def disable_display():
	oled_send([0xAE])

def set_display_contrast(value):
	oled_send([0x81, value])

def set_page_address(page):
	oled_send([0b10110000 | page])

def set_column_address(column):
	oled_send([0b00010000 | ((column >> 4) & 0b00001111), 0b00000000 | (column & 0b00001111)])

def clear_display():
	for page in range(0,8):
		set_page_address(page)
		set_column_address(0)
		oled_send_ram_data([0x00 for i in range(128)])

# deprecated
def picture_to_ram_data(picture):
	# todo fill short pages with zeros
	ram_data = []
	pages_height = int(math.ceil(len(picture)/8))
	for i in range(0, pages_height):
		if i > 7:
			break
		#print 'page '+str(i)
		ram_data.append([])
		for ii in range(0, 8):
			#print '\trow '+str(ii)
			row_addr = i*8+ii
			if row_addr <= len(picture)-1:
				row = picture[row_addr]
			else:
				break
			for j in range(0, len(row)):
				value = row[j]
				#print '\t\tbyte '+str(j)+' - value '+str(value)
				for jj in reversed(range(0, 8)):
					bit_value = (value >> jj) & 0b00000001
					byte_addr = j*8+(7-jj)
					if len(ram_data[i]) < byte_addr+1:
						ram_data[i].append(0x00)
					#print '\t\t\tbit '+str(jj)+' - bit value '+str(bit_value)+' - byte_addr '+str(byte_addr)
					ram_data[i][byte_addr] = ram_data[i][byte_addr] | (bit_value << ii)
					#print '\t\t\t'+str(ram_data[i][byte_addr])
	return ram_data

def draw(ram_data, x, y):
	start_page = int(math.floor(y / 8))
	start_column = x
	if start_page > 7 or start_column > 127:
		return
	total_pages = len(ram_data)
	page_inner_offset = y % 8
	#print 'page_inner_offset: '+str(page_inner_offset)

	if page_inner_offset > 0:
		shifted_ram_data = []
		width = len(ram_data[0])
		next_page = [0x00 for i in range(width)]
		for j in range(0, total_pages):
			page = ram_data[j]
			for i in range(0, len(page)):
				pp = page[i] << page_inner_offset
				pp1 = pp & 0x00FF
				pp2 = (pp & 0xFF00) >> 8
				page[i] = pp1 | next_page[i]
				next_page[i] = pp2
			shifted_ram_data.append(page)
		shifted_ram_data.append(next_page) # todo check emptyness
		total_pages += 1
	else:
		shifted_ram_data = ram_data

	for data_page in range(0, total_pages):
		screen_page = data_page + start_page
		if screen_page > 7:
			break
		#print 'page '+str(screen_page)+' column '+str(start_column)
		set_page_address(screen_page)
		set_column_address(start_column)
		oled_send_ram_data(shifted_ram_data[data_page])

# ===================================================================

def show_humidity(value):
	sprite_icon = sprites['WeatherIcons-Regular-32'][unichr(0xF07A)]
	draw(sprite_icon, 15, 10)

def show_temperature(value):
	sprite_icon = sprites['WeatherIcons-Regular-32'][unichr(0xF055)]
	sprite_degree = sprites['WeatherIcons-Regular-32'][unichr(0xF03C)]

	draw(sprite_icon, 15, 10)
	if value != 0:
		sign = '+' if value > 0 else '-'
		sign_sprite = sprites['NotoSansMono-Regular-18'][sign]
		draw(sign_sprite, 45, 18)

	value = abs(value)
	digits = []
	digits.append(int(math.floor(value / 10)))
	digits.append(value % 10)
	i = 0
	from_x = 57
	for digit in digits:
		if digit == 0:
			continue
		digit_sprite = sprites['NotoSansMono-Regular-18'][unichr(digit+0x30)]
		from_x = from_x+i*11
		draw(digit_sprite, from_x, 18)
		i += 1
	draw(sprite_degree, from_x+15, 10)

# ===================================================================

MODE_TEMPERATURE = 0x01
MODE_HUMIDITY = 0x00
current_mode = MODE_TEMPERATURE


humidity = 72
temperature = 14


set_display_contrast(52)
#clear_display()
#enable_display()

print 'Loading sprites...'
with open('sprites.pickle', 'rb') as f:
	sprites = pickle.load(f)
	print 'Sprites loaded'

dht22_temp_path = '/sys/devices/platform/humidity_sensor/iio:device0/in_temp_input'
dht22_humidity_path = '/sys/devices/platform/humidity_sensor/iio:device0/in_humidityrelative_input'

event_file_path = "/dev/input/event0"
event_format = 'llHHI'
event_struct_size = struct.calcsize(event_format)
fd = os.open(event_file_path, os.O_RDONLY) 
while 1:
	event_data = os.read(fd, event_struct_size)
	(False,False,etype,code,value) = struct.unpack(event_format, event_data)

	#if etype != 0 or code != 0 or value != 0:
		#print("Event type %u, code %u, value %u" % (etype, code, value))

	if etype != 0 and value == 1:
		if code == 59: # KEY_F1
			clear_display()
			if current_mode == MODE_TEMPERATURE:
				show_humidity(humidity)
			else:
				show_temperature(temperature)
			current_mode = ~current_mode & 0x01
			enable_display()
		if code == 60: # KEY_F2
			disable_display()

disable_display()
bus.close()
os.close(fd) 
