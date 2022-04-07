CREATE TABLE `xml_bills` (
  `id` int NOT NULL AUTO_INCREMENT,
  `title` varchar(255) CHARACTER SET utf8 COLLATE utf8_unicode_ci DEFAULT NULL,
  `text` longtext CHARACTER SET utf8 COLLATE utf8_unicode_ci,
  `simhash` blob NOT NULL,
  `simhash_value` bigint unsigned NOT NULL,
  `origin` varchar(255) CHARACTER SET utf8 COLLATE utf8_unicode_ci DEFAULT NULL,
  `pagenum` int DEFAULT NULL,
  `paragraph` varchar(100) COLLATE utf8_unicode_ci DEFAULT NULL,
  `xml_id` varchar(50) COLLATE utf8_unicode_ci DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `id_UNIQUE` (`id`),
  KEY `simhash_value_index` (`simhash_value`)
) ENGINE=InnoDB AUTO_INCREMENT=13882 DEFAULT CHARSET=utf8mb3 COLLATE=utf8_unicode_ci