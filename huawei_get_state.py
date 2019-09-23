#!/usr/bin/python
# -*- coding: utf-8 -*-

import os
import json
import requests
import argparse
import time
import subprocess
import tempfile
import sys
import urllib3
urllib3.disable_warnings()
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
#from requests.packages.urllib3.exceptions import InsecureRequestWarning
#requests.packages.urllib3.disable_warnings(InsecureRequestWarning)


def api_connect(api_user, api_password, api_ip, api_port):
	api_url = "https://{0}:{1}/deviceManager/rest/xxxxx/sessions".format(api_ip, api_port)
	api_data = json.dumps({'scope': '0', 'username': api_user, 'password': api_password})
	headers = {'Connection': 'keep-alive', 'Content-Type': 'application/json', 'Accept': 'application/json'}

	api_connect = requests.post(api_url, verify=False, data = api_data, headers = headers)
	api_connect_info = (json.loads(api_connect.content.decode('utf8')),api_connect.cookies) #Decode нужен потому что объект имеет тип bytes
	return api_connect_info



def api_logout(api_ip, api_port, api_cookies, device_id, iBaseToken):
	headers = {'Connection': 'keep-alive', 'Content-Type': 'application/json', 'Accept': 'application/json', 'iBaseToken':iBaseToken}
	api_url_exit = "https://{0}:{1}/deviceManager/rest/{2}/sessions".format(api_ip, api_port, device_id)
	exit = requests.delete(api_url_exit, verify=False, headers = headers, cookies = api_cookies)

	convert_exit = json.loads(exit.content.decode('utf8'))
	return  convert_exit['error']['code']



def convert_to_zabbix_json(data):
	output = json.dumps({"data": data}, indent = None, separators = (',',': '))
	return output



def send_data_to_zabbix(zabbix_data, storage_name):
	sender_command = "/usr/bin/zabbix_sender"
	config_path = "/etc/zabbix/zabbix_agentd.conf"
	time_of_create_file = int(time.time())
	temp_file = "/tmp/{0}_{1}.tmp".format(storage_name, time_of_create_file)

	with open(temp_file, "w") as f:
		f.write("")
		f.write("\n".join(zabbix_data))

	send_code = subprocess.call([sender_command, "-c", config_path, "-s", storage_name, "-T", "-i", temp_file], stdout = subprocess.PIPE, stderr = subprocess.PIPE)
	os.remove(temp_file)
	return send_code



def discovering_resources(api_user, api_password, api_ip, api_port, storage_name, list_resources):
	api_connection = api_connect(api_user, api_password, api_ip, api_port)
	
	device_id = api_connection[0]['data']['deviceid']
	iBaseToken = api_connection[0]['data']['iBaseToken']
	api_cookies = api_connection[1]

	somethings = []
	for resource in list_resources:
		resource_url = "https://{0}:{1}/deviceManager/rest/{2}/{3}".format(api_ip, api_port, device_id, resource)
		resource_info = requests.get(resource_url, verify=False, cookies = api_cookies)
		resource_info = json.loads(resource_info.content.decode('cp1251')) # Конвертация из JSON-объекта в словарь


		discovered_resource = []
		for one_res in resource_info['data']:
			resources_list = dict()
			if resource == 'disk':
				resources_list["{#ID}"] = one_res['ID']
				resources_list["{#LOCATION}"] = one_res['LOCATION'].replace(' ', '_')
				discovered_resource.append(resources_list)
			elif ['diskpool', 'storagepool', 'lun'].count(resource) == 1:
				resources_list["{#NAME}"] = one_res['NAME'].replace(' ','_')
				discovered_resource.append(resources_list)
			else:
				resources_list["{#NAME}"] = one_res['NAME'].replace(' ','_')
				resources_list["{#ID}"] = one_res['ID']
				resources_list["{#LOCATION}"] = one_res['LOCATION'].replace(' ','_')
				discovered_resource.append(resources_list)

		converted_resource = convert_to_zabbix_json(discovered_resource)
		timestampnow = int(time.time())
		somethings.append("%s %s %s %s" % (storage_name, resource, timestampnow, converted_resource))

	exit_code = api_logout(api_ip, api_port, api_cookies, device_id, iBaseToken)
#        if exit_code != 0:
#		return 5

	return send_data_to_zabbix(somethings, storage_name)
	



def get_status_resources(api_user, api_password, api_ip, api_port, storage_name, list_resources):
	api_connection = api_connect(api_user, api_password, api_ip, api_port)

	device_id = api_connection[0]['data']['deviceid']
	iBaseToken = api_connection[0]['data']['iBaseToken']
	api_cookies = api_connection[1]


	state_resources = [] # В этот список будут складываться состояние каждого ресурса (объекта) в формате zabbix
	for resource in list_resources:
		resource_url = "https://{0}:{1}/deviceManager/rest/{2}/{3}".format(api_ip, api_port, device_id, resource)
		resource_info = requests.get(resource_url, verify=False, cookies = api_cookies)
		resource_info = json.loads(resource_info.content.decode('cp1251')) # Конвертация из JSON-объекта в словарь
		timestampnow = int(time.time())

		if ['fc_port','sas_port', 'eth_port'].count(resource) == 1:
			for one_res in resource_info['data']:
				key_health = "health.{0}.[{1}]".format(resource, one_res['LOCATION'].replace(' ','_'))  # Создаем ключ для каждого объекта и заменяем пробелы
				key_status = "running.{0}.[{1}]".format(resource, one_res['LOCATION'].replace(' ','_'))  # Создаем ключ для каждого объекта и заменяем пробелы
				state_resources.append("%s %s %s %s" % (storage_name, key_health, timestampnow, one_res['HEALTHSTATUS']))
				state_resources.append("%s %s %s %s" % (storage_name, key_status, timestampnow, one_res['RUNNINGSTATUS']))
		elif ['diskpool'].count(resource) == 1:
			for one_res in resource_info['data']:
				key_health = "health.{0}.[{1}]".format(resource, one_res['NAME'])
				key_status = "running.{0}.[{1}]".format(resource, one_res['NAME'])
				state_resources.append("%s %s %s %s" % (storage_name, key_health, timestampnow, one_res['HEALTHSTATUS']))
				state_resources.append("%s %s %s %s" % (storage_name, key_status, timestampnow, one_res['RUNNINGSTATUS']))
		elif ['lun'].count(resource) == 1:
			subscribed_capacity_pools = {} # Здесь будет: имя пула - сумма объемов лунов, принадлежащих этому пулу
			for one_res in resource_info['data']:
				key_health = "health.{0}.[{1}]".format(resource, one_res['NAME'])
				key_status = "running.{0}.[{1}]".format(resource, one_res['NAME'])
				state_resources.append("%s %s %s %s" % (storage_name, key_health, timestampnow, one_res['HEALTHSTATUS']))
				state_resources.append("%s %s %s %s" % (storage_name, key_status, timestampnow, one_res['RUNNINGSTATUS']))


				# Блок кода, подсчитывает сумму "выделенных объемов" лунов для каждого пула. Нужно для подсчета подписанного места на каждом пуле
				pool_name = one_res['PARENTNAME']
				abr = list(subscribed_capacity_pools.keys()) #Конвертируем ключи словаря в список, что бы было легче сравнивать
				if abr.count(pool_name) == 0: #А есть ли в словаре такой лун?
					subscribed_capacity_pools[pool_name] = 0 #Нету луна? добавь его имя как ключ в словарь. Начальное значение = 0, сюда суммируются объемы лунов
				capacity_lun_in_blocks = int(one_res['CAPACITY']) # Конвертируем из строки в число
				size_block = int(one_res['SECTORSIZE'])
				subscribed_capacity_pools[pool_name] += capacity_lun_in_blocks * size_block # Умножением переводим из блоков в байты


			# Формируется формат zabbix для подписанного места из словаря
			for key in subscribed_capacity_pools.keys():
				key_subscribed_capacity = "subscribed.capacity.{0}.[{1}]".format('storagepool', key) # key - принимает имя пула
				state_resources.append("%s %s %s %s" %(storage_name, key_subscribed_capacity, timestampnow, subscribed_capacity_pools[key]))

		elif ['storagepool'].count(resource) == 1:
			for one_res in resource_info['data']:
				key_health = "health.{0}.[{1}]".format(resource, one_res['NAME'])
				key_status = "running.{0}.[{1}]".format(resource, one_res['NAME'])
				key_total_capacity = "total.capacity.{0}.[{1}]".format(resource, one_res['NAME'])
				key_free_capacity = "free.capacity.{0}.[{1}]".format(resource, one_res['NAME'])
				key_used_capacity = "used.capacity.{0}.[{1}]".format(resource, one_res['NAME'])

				state_resources.append("%s %s %s %s" % (storage_name, key_health, timestampnow, one_res['HEALTHSTATUS']))
				state_resources.append("%s %s %s %s" % (storage_name, key_status, timestampnow, one_res['RUNNINGSTATUS']))
				state_resources.append("%s %s %s %s" % (storage_name, key_total_capacity, timestampnow, int(one_res['USERTOTALCAPACITY']) * 512))
				state_resources.append("%s %s %s %s" % (storage_name, key_free_capacity, timestampnow, int(one_res['USERFREECAPACITY']) * 512))
				state_resources.append("%s %s %s %s" % (storage_name, key_used_capacity, timestampnow, int(one_res['USERCONSUMEDCAPACITY']) * 512))

				"""
				Обход момента, когда в пуле нет лунов (т.е. used_capacity пула  равен нулю).
				Когда нет лунов в пуле, невозможно вычислить подписанное место,
				т.к. подписанное место вычисляется в разделе лунов путем сложения total_capacity всех лунов, принадлежащих данному пулу.
				"""
				if int(one_res['USERCONSUMEDCAPACITY']) == 0:
					key_subscribed_capacity = "subscribed.capacity.{0}.[{1}]".format(resource,one_res['NAME'])
					state_resources.append("%s %s %s %s" % (storage_name, key_subscribed_capacity, timestampnow, 0))

		else:
			for one_res in resource_info['data']:
				key_health = "health.{0}.[{1}]".format(resource, one_res['LOCATION'].replace(' ','_'))  # Создаем ключ для каждого объекта и заменяем пробелы
				key_status = "running.{0}.[{1}]".format(resource, one_res['LOCATION'].replace(' ','_'))
				state_resources.append("%s %s %s %s" % (storage_name, key_health, timestampnow, one_res['HEALTHSTATUS']))
				state_resources.append("%s %s %s %s" % (storage_name, key_status, timestampnow, one_res['RUNNINGSTATUS']))

	exit_code = api_logout(api_ip, api_port, api_cookies, device_id, iBaseToken)
#        if exit_code != 0:
#               return 5
#	print (state_resources)
	return send_data_to_zabbix(state_resources, storage_name)


def main():

	huawei_parser = argparse.ArgumentParser()
	huawei_parser.add_argument('--api_ip', action="store", help="Where to connect", required=True)
	huawei_parser.add_argument('--api_port', action="store", required=True)
	huawei_parser.add_argument('--api_user', action="store", required=True)
	huawei_parser.add_argument('--api_password', action="store", required=True)
	huawei_parser.add_argument('--storage_name', action="store", required=True)

	group = huawei_parser.add_mutually_exclusive_group(required=True)
	group.add_argument('--discovery', action ='store_true')
	group.add_argument('--status', action='store_true')
	arguments = huawei_parser.parse_args()


	list_resources = ['disk', 'power', 'enclosure', 'controller', 'backup_power', 'expboard', 'intf_module', 'eth_port', 'sas_port', 'fc_port', 'fan', 'lun', 'diskpool', 'storagepool']

	if arguments.discovery:
		result_discovery = discovering_resources(arguments.api_user, arguments.api_password, arguments.api_ip, arguments.api_port, arguments.storage_name, list_resources)
		print result_discovery
	elif arguments.status:
		result_status = get_status_resources(arguments.api_user, arguments.api_password, arguments.api_ip, arguments.api_port, arguments.storage_name, list_resources)
		print result_status


if __name__ == "__main__":
	main()
