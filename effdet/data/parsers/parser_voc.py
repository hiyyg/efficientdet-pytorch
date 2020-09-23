""" Pascal VOC dataset parser

Copyright 2020 Ross Wightman
"""
import os
import xml.etree.ElementTree as ET
from collections import defaultdict
import numpy as np

from .parser_config import VocParserCfg


class VocParser:

    DEFAULT_CLASSES = (
        'aeroplane', 'bicycle', 'bird', 'boat', 'bottle', 'bus', 'car', 'cat', 'chair',
        'cow', 'diningtable', 'dog', 'horse', 'motorbike', 'person', 'pottedplant',
        'sheep', 'sofa', 'train', 'tvmonitor')

    def __init__(self, cfg: VocParserCfg):
        self.yxyx = cfg.bbox_yxyx
        self.has_labels = cfg.has_labels
        self.keep_difficult = cfg.keep_difficult
        self.include_bboxes_ignore = False
        self.ignore_empty_gt = self.has_labels and cfg.ignore_empty_gt
        self.min_img_size = cfg.min_img_size
        self.correct_bbox = 1

        classes = cfg.classes or self.DEFAULT_CLASSES
        self.cat_ids = []
        self.cat_to_label = {cat: i + 1 for i, cat in enumerate(classes)}
        self.img_ids = []
        self.img_ids_invalid = []
        self.img_infos = []
        self.img_id_to_idx = {}

        self.anns = None
        self._load_annotations(cfg)

    def _load_annotations(self, cfg: VocParserCfg):

        with open(cfg.split_filename) as f:
            ids = f.readlines()
        self.anns = []

        for img_idx, img_id in enumerate(ids):
            img_id = img_id.strip("\n")
            filename = cfg.img_filename % img_id
            xml_path = cfg.ann_filename % img_id
            tree = ET.parse(xml_path)
            root = tree.getroot()
            size = root.find('size')
            width = int(size.find('width').text)
            height = int(size.find('height').text)
            if min(width, height) < self.min_img_size:
                continue

            anns = []
            for obj_idx, obj in enumerate(root.findall('object')):
                name = obj.find('name').text
                label = self.cat_to_label[name]
                difficult = int(obj.find('difficult').text)
                bnd_box = obj.find('bndbox')
                bbox = [
                    int(bnd_box.find('xmin').text),
                    int(bnd_box.find('ymin').text),
                    int(bnd_box.find('xmax').text),
                    int(bnd_box.find('ymax').text)
                ]
                anns.append(dict(label=label, bbox=bbox, difficult=difficult))

            if not self.ignore_empty_gt or len(anns):
                self.anns.append(anns)
                self.img_infos.append(dict(id=img_id, file_name=filename, width=width, height=height))
                self.img_ids.append(img_id)
                self.img_id_to_idx[img_id] = img_idx
            else:
                self.img_ids_invalid.append(img_id)

    def merge(self, other):
        this_size = len(self.img_ids)
        assert len(self.cat_ids) == len(other.cat_ids)
        self.img_ids.extend(other.img_ids)
        self.img_infos.extend(other.img_infos)
        self.anns.extend(other.anns)
        for id, idx in other.img_id_to_idx.items():
            self.img_id_to_idx[id] = idx + this_size

    def get_ann_info(self, idx):
        return self._parse_ann_info(self.anns[idx])

    def _parse_ann_info(self, ann_info):
        bboxes = []
        labels = []
        bboxes_ignore = []
        labels_ignore = []
        for ann in ann_info:
            ignore = False
            x1, y1, x2, y2 = ann['bbox']
            label = ann['label']
            w = x2 - x1
            h = y2 - y1
            if w < 1 or h < 1:
                ignore = True
            if self.yxyx:
                bbox = [y1, x1, y2, x2]
            else:
                bbox = ann['bbox']
            if ignore or (ann['difficult'] and not self.keep_difficult):
                bboxes_ignore.append(bbox)
                labels_ignore.append(label)
            else:
                bboxes.append(bbox)
                labels.append(label)

        if not bboxes:
            bboxes = np.zeros((0, 4), dtype=np.float32)
            labels = np.zeros((0, ), dtype=np.float32)
        else:
            bboxes = np.array(bboxes, ndmin=2, dtype=np.float32) - 1
            labels = np.array(labels, dtype=np.float32)

        if self.include_bboxes_ignore:
            if not bboxes_ignore:
                bboxes_ignore = np.zeros((0, 4), dtype=np.float32)
                labels_ignore = np.zeros((0, ), dtype=np.float32)
            else:
                bboxes_ignore = np.array(bboxes_ignore, ndmin=2, dtype=np.float32) - 1
                labels_ignore = np.array(labels_ignore, dtype=np.float32)

        ann = dict(
            bbox=bboxes.astype(np.float32),
            cls=labels.astype(np.int64))

        if self.include_bboxes_ignore:
            ann.update(dict(
                bbox_ignore=bboxes_ignore.astype(np.float32),
                cls_ignore=labels_ignore.astype(np.int64)))
        return ann

