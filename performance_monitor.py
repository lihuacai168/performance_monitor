#!/usr/bin/env python
# -*- coding:utf-8 -*-
# Author: leeyoshinari
# Monitoring
import os
import pymysql
import time
import threading
import config as cfg

lock = threading.Lock()


class PerMon(object):
    def __init__(self):
        self._is_run = 0
        self.is_jar = cfg.IS_JAR
        self.counter = 0    # Record the failure times of commands run error.
        self._pid = []
        self.db = None
        self.cursor = None
        self._total_time = 0
        self.interval = int(cfg.INTERVAL)
        self.disk = cfg.DISK

        self.cpu_cores = 0  # CPU core number
        self.total_mem = 0  # total memory

        self.mysql_ip = cfg.MySQL_IP
        self.mysql_username = cfg.MySQL_USERNAME
        self.mysql_password = cfg.MySQL_PASSWORD
        self.database_name = cfg.MySQL_DATABASE

        self.get_cpu_cores()
        self.get_total_mem()

        self.start_time = 0

    @property
    def is_run(self):
        return self._is_run

    @is_run.setter
    def is_run(self, value):
        self._is_run = value

    @property
    def pid(self):
        return self._pid

    @pid.setter
    def pid(self, value):
        self._pid = value

    @property
    def total_time(self):
        return self._total_time

    @total_time.setter
    def total_time(self, value):
        self._total_time = value + 200

    def connect_mysql(self):
        """
        Connecting MySQL, and create tables.
        """
        if self.db is None:
            self.db = pymysql.connect(self.mysql_ip, self.mysql_username, self.mysql_password, self.database_name)
            self.cursor = self.db.cursor()

        cpu_and_mem_sql = 'CREATE TABLE IF NOT EXISTS cpu_and_mem (id INT NOT NULL PRIMARY KEY auto_increment, pid INT, time DATETIME, cpu FLOAT, mem FLOAT, jvm FLOAT);'
        io_sql = 'CREATE TABLE IF NOT EXISTS io (id INT NOT NULL PRIMARY KEY auto_increment, pid INT, time DATETIME, r_s FLOAT, w_s FLOAT, util FLOAT, d_r FLOAT, d_w FLOAT, d_util FLOAT);'
        handle_sql = 'CREATE TABLE IF NOT EXISTS handles (id INT NOT NULL PRIMARY KEY auto_increment, pid INT, time DATETIME, handles FLOAT);'

        lock.acquire()
        self.cursor.execute(cpu_and_mem_sql)
        self.cursor.execute(io_sql)
        self.cursor.execute(handle_sql)
        self.db.commit()
        lock.release()

    def write_cpu_mem(self):
        """
        Monitoring CPU and memory.
        """
        while True:
            if self._is_run == 1 or self._is_run == 2:
                self.connect_mysql()
                self.start_time = time.time()
                start_search_time = time.time()

                while True:
                    if time.time() - self.start_time < self._total_time:
                        get_data_time = time.time()
                        if get_data_time - start_search_time > self.interval:
                            start_search_time = get_data_time
                            if self.counter > cfg.RUN_ERROR_TIMES:
                                self._is_run = 0    # if the times of failure is larger than default, stop monitor.
                                break

                            try:
                                for pid in self._pid:
                                    cpu, mem = self.get_cpu(pid)
                                    if cpu is None:
                                        continue

                                    if self.is_jar:
                                        jvm = self.get_mem(pid)
                                    else:
                                        jvm = 0
                                    search_time = time.strftime('%Y-%m-%d %H:%M:%S')

                                    self.write_in_sql(search_time, pid, cpu, [mem, jvm], 0, 0, 'cpu_and_mem')

                                self.counter = 0

                            except Exception as err:
                                print('Error: cpu_and_mem {}.'.format(err))
                                self.counter += 1
                                continue

                    else:
                        self._is_run = 0    # if the total time is up, stop monitor.
                        break

                    if self._is_run == 0:   # if _is_run=0, stop monitor.
                        break
            else:
                time.sleep(cfg.SLEEPTIME)

    def write_io(self):
        while True:
            if self._is_run == 1 or self._is_run == 2:
                self.connect_mysql()
                self.start_time = time.time()

                while True:
                    if time.time() - self.start_time < self._total_time:
                        if self.counter > cfg.RUN_ERROR_TIMES:
                            self._is_run = 0
                            break

                        try:
                            for ipid in self._pid:
                                ioer = self.get_io(ipid)

                                io_time = time.strftime('%Y-%m-%d %H:%M:%S')

                                self.write_in_sql(io_time, ipid, 0, 0, ioer, 0, 'io')

                            self.counter = 0

                        except Exception as err:
                            print('Error: io {}.'.format(err))
                            self.counter += 1
                            continue

                    else:
                        self._is_run = 0
                        break

                    if self._is_run == 0:
                        break
            else:
                time.sleep(cfg.SLEEPTIME)

    def write_handle(self):
        while True:
            if self._is_run == 1 or self._is_run == 2:
                self.connect_mysql()
                self.start_time = time.time()

                while True:
                    if time.time() - self.start_time < self._total_time:
                        if self.counter > cfg.RUN_ERROR_TIMES:
                            self._is_run = 0
                            break

                        try:
                            for hpid in self._pid:
                                handles = self.get_handle(hpid)
                                if handles is None:
                                    continue

                                handle_time = time.strftime('%Y-%m-%d %H:%M:%S')

                                self.write_in_sql(handle_time, hpid, 0, 0, 0, handles, 'handles')

                            self.counter = 0

                        except Exception as err:
                            print('Error:{}.'.format(err))
                            self.counter += 1
                            continue

                    else:
                        self._is_run = 0
                        break

                    if self._is_run == 0:
                        break
            else:
                time.sleep(cfg.SLEEPTIME)

    def get_cpu(self, pid):
        """
        Get CPU and Memory of specified PID. It uses `top`.
        It returns CPU(%), and Memory(G).
        """
        result = os.popen('top -n 1 -b |grep -P {} |tr -s " "'.format(pid)).readlines()[0]
        res = result.strip().split(' ')

        cpu = None
        mem = None
        if str(pid) in res:
            ind = res.index(str(pid))
            cpu = float(res[ind + 8]) / self.cpu_cores
            mem = float(res[ind + 9]) * self.total_mem

        return cpu, mem

    def get_mem(self, pid):
        """
        Get JVM of specified PID. It uese `jstat`.
        It returns JVM(G).
        """
        result = os.popen('jstat -gc {} |tr -s " "'.format(pid)).readlines()[1]
        res = result.strip().split(' ')

        mem = float(res[2]) + float(res[3]) + float(res[5]) + float(res[7])

        return mem / 1024 / 1024

    def get_io(self, pid):
        """
        Get IO of specified PID. It uses `iotop`.
        It returns IO(%).
        """
        # get rkB/s and wkB/s.
        result = os.popen('iotop -n 2 -d 1 -b -qqq -p {} -k |tr -s " "'.format(pid)).readlines()[-1]
        res = result.strip().split(' ')

        disk_r, disk_w, disk_util = self.get_disk_io()

        writer = None
        reader = None
        if str(pid) in res:
            ind = res.index(str(pid))
            writer = float(res[ind + 3])
            reader = float(res[ind + 5])

        # IO of PID
        try:
            ratio_w = writer / disk_w * disk_util
            ratio_r = reader / disk_r * disk_util
        except Exception as err:
            ratio_w = 0
            ratio_r = 0

        return [reader, writer, disk_r, disk_w, disk_util, max(ratio_r, ratio_w)]

    def get_disk_io(self):
        """
        Get IO of disk. It uses `iostat`.
        It returns disk_r(kB/s), disk_w(kB/s) and disk_util(%).
        """
        result = os.popen('iostat -d -x -k {} 1 2 |tr -s " "'.format(self.disk)).readlines()
        res = [line for line in result if self.disk in line]
        disk_res = res[-1].strip().split(' ')

        disk_r = None
        disk_w = None
        disk_util = None
        if self.disk in disk_res:
            disk_r = float(disk_res[5])
            disk_w = float(disk_res[6])
            disk_util = float(disk_res[-1])

        return disk_r, disk_w, disk_util

    def get_handle(self, pid):
        """
        Get handles of specified PID. It uses `lsof`.
        It returns handles number.
        """
        result = os.popen("lsof -n | awk '{print $2}'| sort | uniq -c | sort -nr | " + "grep {}".format(pid)).readlines()
        res = result[0].strip().split(' ')
        handles = None
        if str(pid) in res:
            handles = int(res[0])

        return handles

    def get_cpu_cores(self):
        """
        Get CPU core number.
        """
        result = os.popen('cat /proc/cpuinfo| grep "processor"| wc -l').readlines()[0]

        self.cpu_cores = int(result)

    def get_total_mem(self):
        """
        Ger total memory.
        """
        result = os.popen('cat /proc/meminfo| grep "MemTotal"| uniq').readlines()[0]

        self.total_mem = float(result.split(':')[-1].split('k')[0].strip()) / 1024 / 1024 / 100

    def write_in_sql(self, search_time, pid, cpu, mem, ioer, handles, dbname):
        """
        Write the data of monitoring into MySQL.
        """
        if self.db is None:     # If MySQL connection is broken, reconnect.
            self.db = pymysql.connect(self.mysql_ip, self.mysql_username, self.mysql_password, self.database_name)
            self.cursor = self.db.cursor()

        if dbname == 'cpu_and_mem':
            sql = "INSERT INTO {}(id, pid, time, cpu, mem, jvm) VALUES (default, {}, '{}', {}, {}, {});".format(dbname, pid, search_time, cpu, mem[0], mem[1])
        if dbname == 'io':
            sql = "INSERT INTO {}(id, pid, time, r_s, w_s, util, d_r, d_w, d_util) VALUES (default, {}, '{}', {}, {}, {}, {}, {}, {});".format(dbname, pid, search_time, ioer[0], ioer[1], ioer[-1], ioer[2], ioer[3], ioer[4])
        if dbname == 'handles':
            sql = "INSERT INTO {}(id, pid, time, handles) VALUES (default, {}, '{}', {});".format(dbname, pid, search_time, handles)

        lock.acquire()
        try:
            self.cursor.execute(sql)
            self.db.commit()
        except Exception as err:
            print(err)
            self.db.rollback()
        lock.release()

    def __del__(self):
        pass
