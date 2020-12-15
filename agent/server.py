#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Author: leeyoshinari

import os
import time
import asyncio
import traceback
from aiohttp import web
from common import get_ip
from logger import logger, cfg
from performance_monitor import PerMon, port_to_pid

permon = PerMon()
HOST = cfg.getServer('host') if cfg.getServer('host') else get_ip()

async def index(request):
	"""
	首页，浏览器访问 http://ip:port 即可显示服务器基本资源
	:param request:
	:return:
	"""
	return web.Response(
		body=f'当前服务器系统版本为{permon.system_version}，{permon.cpu_info}，总内存为{permon.total_mem}G，'
			 f'使用的网卡为{permon.nic}，系统带宽为{permon.network_speed}Mb/s，共有{len(permon.all_disk)}个磁盘，'
			 f'磁盘总大小为{permon.total_disk_h}，磁盘号分别为{"、".join(permon.all_disk)}。如需停止监控客户端，'
			 f'请访问 http://{HOST}:{cfg.getServer("port")}/stop')


async def run_monitor(request):
	"""
	开始监控接口
	:param request:
	:return:
	"""
	try:
		data = await request.json()
		host = data.get('host')
		port = data.get('port')
		network = data.get('net')
		is_run = data.get('isRun')

		if host == HOST:
			if port:
				pid = port_to_pid(port)     # 根据端口号查询进程号
				if pid is None:
					logger.warning(f"端口 {port} 未启动！")
					return web.json_response({
						'code': 1, 'msg': f"端口 {port} 未启动！", 'data': {'host': host, 'port': port, 'pid': None}})

				if is_run == '0':   # 如果是停止监控
					if port in permon.stop['port']:     # 端口是否监控过
						permon.stop = {'port': port, 'pid': pid, 'net': network, 'is_run': 0}
						logger.info('停止监控成功！')
						return web.json_response({
							'code': 0, 'msg': '停止监控成功！', 'data': {'host': host, 'port': port, 'pid': pid}})
					else:
						logger.warning(f"端口 {port} 未监控，请先监控！")
						return web.json_response({
							'code': 1, 'msg': f"端口 {port} 未监控，请先监控！", 'data': {'host': host, 'port': port, 'pid': pid}})

				if is_run == '1':       # 如果是开始监控
					permon.start = {'port': port, 'pid': pid, 'is_run': 1}
					logger.info('开始监控成功！')
					return web.json_response({
						'code': 0, 'msg': '开始监控成功！', 'data': {'host': host, 'port': port, 'pid': pid}})

			else:
				logger.error('请求参数异常')
				return web.json_response({
					'code': 2, 'msg': '请求参数异常', 'data': {'host': host, 'port': port, 'pid': None}})
		else:
			logger.error('请求参数异常')
			return web.json_response({
				'code': 2, 'msg': '请求参数异常', 'data': {'host': host, 'port': port, 'pid': None}})

	except Exception as err:
		logger.error(traceback.format_exc())
		return web.json_response({
			'code': 2, 'msg': err, 'data': {'host': HOST, 'port': None, 'pid': None}})


async def get_monitor(request):
	"""
	获取监控端口列表
	:param request:
	:return:
	"""
	data = await request.json()
	host = data.get('host')
	if host == HOST:
		msg = permon.start
		if len(msg['port']) > 0:    # 是否监控过端口
			data = {'host': [host]*len(msg['port'])}
			data.update(msg)
			return web.json_response({'code': 0, 'msg': '操作成功', 'data': data})
		else:
			logger.error('暂未监控任何端口')
			return web.json_response({
				'code': 1, 'msg': '暂未监控任何端口', 'data': {'host': host, 'port': None, 'pid': None}})
	else:
		logger.error('请求参数异常')
		return web.json_response({
			'code': 2, 'msg': '请求参数异常', 'data': {'host': host, 'port': None, 'pid': None}})


async def get_gc(request):
	"""
	获取java应用系统垃圾回收数据
	:param request:
	:return:
	"""
	port = request.match_info['port']
	try:
		pid = port_to_pid(port)     # 根据端口号查询进程号
		if pid is None:
			logger.warning(f"端口 {port} 未启动！")
			return web.json_response({'code': 1, 'msg': f"端口 {port} 未启动！", 'data': None})

		result = os.popen(f'jstat -gc {pid} |tr -s " "').readlines()[1]     # 执行jstat命令
		res = result.strip().split(' ')

		# 当前gc数据
		ygc = int(res[12])
		ygct = float(res[13])
		fgc = int(res[14])
		fgct = float(res[15])
		fygc = 0
		ffgc = 0

		# 历史gc数据
		fgc_history = permon.FGC[port]
		fgc_time_history = permon.FGC_time[port]
		if fgc > 0:
			if fgc == fgc_history:
				if len(fgc_time_history) > 1:
					ffgc = round(time.time() - fgc_time_history[-2], 2)
				else:
					result = os.popen(f'ps -p {pid} -o etimes').readlines()[1]  # 查询该进程运行时间
					runtime = int(result.strip())
					ffgc = round(runtime / fgc, 2)
			else:
				ffgc = round(time.time() - fgc_time_history[-1], 2)
		else:
			fgc = -1

	except Exception:
		logger.error(traceback.format_exc())
		ygc, ygct, fgc, fgct, fygc, ffgc = -1, -1, -1, -1, -1, -1

	return web.json_response({'code': 0, 'msg': '操作成功', 'data': [ygc, ygct, fgc, fgct, '-', ffgc]})


async def stop_monitor(request):
	pid = port_to_pid(cfg.getServer('port'))
	if pid:
		res = os.popen(f'kill -9 {pid}')
		logger.info('监控客户端停止成功！')
		return web.Response(body='监控客户端停止成功！')
	else:
		return web.Response(body='监控客户端未运行！')


async def main():
	app = web.Application()

	app.router.add_route('GET', '/', index)
	app.router.add_route('GET', '/stop', stop_monitor)
	app.router.add_route('POST', '/runMonitor', run_monitor)
	app.router.add_route('POST', '/getMonitor', get_monitor)
	app.router.add_route('GET', '/getGC/{port}', get_gc)

	runner = web.AppRunner(app)
	await runner.setup()
	site = web.TCPSite(runner, HOST, cfg.getServer('port'))
	await site.start()


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
loop.run_forever()
