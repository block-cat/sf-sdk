#!/usr/bin/python3
# @Time    : 2019-08-21
# @Author  : Kevin Kong (kfx2007@163.com)

import base64
from hashlib import md5
from lxml import etree
import inspect
from itertools import zip_longest
from functools import partial
import requests

URL = "http://bsp-oisp.sf-express.com/bsp-oisp/sfexpressService"

class BaseService(object):

    def __init__(self, func):
        self.func = func

    def __get__(self, instance, owner):
        return partial(self.__call__, instance)

    def __call__(self, *args, **kwargs):
        data = {}
        service = self.__name__
        service_name = self.__name__.split("Service")[0]
        data["service"] = service
        ags = inspect.getfullargspec(self.func).args
        vdata = dict(zip_longest(ags, args))
        data.update(kwargs)
        vdata = {key: value for key,
                 value in vdata.items() if value and key != 'self'}
        data.update({
            "data": {
                service_name: vdata
            }
        })
        return args[0].post(data)


class Service(type):

    def __new__(cls, name, bases=None, attrs={}):
        attrs['__name__'] = name
        return type.__new__(cls, name, (BaseService,), attrs)


class Comm(object):
    """封装公共请求"""

    def __get__(self, instance, owner):
        self._clientcode = instance.clientcode
        self._checkword = instance.checkword
        return self

    def gen_verifycode(self, data):
        """
        生成校验码
        参数：
        data: 传输的报文
        """
        s = "{}{}".format(data, self._checkword)
        return base64.b64encode(md5(s.encode("utf-8")).digest()).decode("utf-8")

    def gen_xmldata(self, data):
        """
        生成xml报文
        """
        root = etree.Element("Request")
        root.set("service", data.get("service", None))
        root.set("lang", data.get("lang", "zh-CN"))
        head = etree.Element("Head")
        head.text = data.get("clientcode", self._clientcode)
        root.append(head)
        body = etree.Element("Body")

        for key, value in data["data"].items():
            # 仅支持二级嵌套
            el = etree.Element(key)
            if type(value) is dict:
                for k, v in value.items():
                    el2 = etree.Element(k)
                    if type(v) is dict:
                        for name, att in v.items():
                            if att:
                                el2.set(name, att)
                        el.append(el2)
                    else:
                        el.set(k, v)
            else:
                el.set(key, value)
            body.append(el)
        root.append(body)
        return etree.tostring(root, xml_declaration=True, encoding="UTF-8").decode("utf-8")

    def _parse(self, root):
        data = {}
        # 如果所有node同名，应该使用List存储
        if len(set([node.tag for node in root.getchildren()])) < len(root.getchildren()):
            first = root.getchildren()[0]
            data[first.tag] = []
            for node in root.getchildren():
                record = {}
                for att, val in node.items():
                    record[att] = val
                data[first.tag].append(record)
                # 获取子节点
                if len(node.getchildren()):
                    # for n in node.getchildren():
                    data[node.tag] = self._parse(node)

        else:
            for node in root.getchildren():
                data[node.tag] = {}
                # 获取属性和属性值
                for att, val in node.items():
                    data[node.tag][att] = val
                # 获取子节点
                if len(node.getchildren()):
                    # for n in node.getchildren():
                    data[node.tag] = self._parse(node)
        # 处理本节点的属性
        for att, val in root.items():
            data[att] = val
        return data

    def parse_response(self, data):
        """
        解析响应结果
        """
        res = {}
        root = etree.fromstring(data)
        head = root.xpath("//Head")[0].text
        if head == "ERR":
            # 发生错误，停止解析
            res["result"] = 1
            res["msg"] = root.xpath("//ERROR")[0].text

        if head == "OK":
            # 返回成功
            body = root.xpath("//Body")[0]
            data = self._parse(body)
            res["result"] = 0
            res["data"] = data

        return res

    def post(self, data):
        """
        提交请求
        """
        xml = self.gen_xmldata(data)
        post_data = {
            "xml": xml,
            "verifyCode": self.gen_verifycode(xml)
        }

        response = requests.post(URL, post_data)
        return self.parse_response(response.content)
