# zabbix-huawei-storages
Python script for monitoring huawei storages

Tested on   5500 V5, 5600 V5, 2600 V3, 5500 V3, dorado 5000 V3, 18800 V3

Macros on zabbix template:
{$API_USER} - user on stroage. It have "Level" as read-only user, "Role" as Administrator
{$API_PASSWORD} - password for {$API_USER}
{$API_PORT} - port of api

To make discovery of object need run script on linux console ./huawei_get_state.py --api_ip=xxx.xxx.xxx.xxx --api_port=8088 --api_user=username --api_password='password' --storage_name="storage_name_in_zabbix" --discovery
Script must return 0 in case of success

To get value of metrics nedd run script on linux console ./huawei_get_state.py --api_ip=xxx.xxx.xxx.xxx --api_port=8088 --api_user=username --api_password='password' --storage_name="storage_name_in_zabbix" --status
Script must return 0 in case of success
