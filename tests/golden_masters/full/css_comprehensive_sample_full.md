# CSS Analysis: examples/comprehensive_sample.css

## Document Overview

| Property | Value |
|----------|-------|
| File | examples/comprehensive_sample.css |
| Language | css |
| Total Lines | 1478 |
| Total Elements | 245 |

## CSS Rules

| Selector | Class | Properties | Lines |
|----------|-------|------------|-------|
| `:root` | typography | 38 props | 7-61 |
| `*,
*::before,
*::after` | box_model | 1 props | 68-72 |
| `*` | box_model | 2 props | 75-78 |
| `article,
aside,
details,
figcaption,
fig` | layout | 1 props | 81-94 |
| `html` | typography | 5 props | 101-107 |
| `body` | typography | 7 props | 110-118 |
| `h1, h2, h3, h4, h5, h6` | typography | 5 props | 125-131 |
| `h1` | box_model | 2 props | 133-136 |
| `h2` | typography | 1 props | 138-140 |
| `h3` | typography | 1 props | 142-144 |
| `h4` | typography | 1 props | 146-148 |
| `h5` | typography | 1 props | 150-152 |
| `h6` | typography | 1 props | 154-156 |
| `p` | box_model | 2 props | 159-162 |
| `strong,
b` | typography | 1 props | 165-168 |
| `em,
i` | typography | 1 props | 170-173 |
| `mark` | box_model | 4 props | 176-181 |
| `code,
kbd,
pre,
samp` | typography | 2 props | 184-190 |
| `code` | box_model | 4 props | 192-197 |
| `pre` | box_model | 6 props | 199-206 |
| `pre code` | typography | 3 props | 208-212 |
| `blockquote` | box_model | 5 props | 215-221 |
| `blockquote p:last-child` | box_model | 1 props | 223-225 |
| `blockquote footer` | typography | 3 props | 227-231 |
| `blockquote footer::before` | other | 1 props | 233-235 |
| `a` | typography | 3 props | 241-245 |
| `a:hover,
a:focus` | typography | 2 props | 247-251 |
| `a:focus` | other | 2 props | 253-256 |
| `a[target="_blank"]::after` | typography | 3 props | 259-263 |
| `ul,
ol` | box_model | 2 props | 269-273 |
| `li` | box_model | 1 props | 275-277 |
| `ul ul,
ol ol,
ul ol,
ol ul` | box_model | 2 props | 280-286 |
| `dl` | box_model | 1 props | 289-291 |
| `dt` | box_model | 2 props | 293-296 |
| `dd` | box_model | 2 props | 298-301 |
| `table` | box_model | 7 props | 307-315 |
| `caption` | typography | 4 props | 317-322 |
| `th,
td` | box_model | 3 props | 324-329 |
| `th` | typography | 3 props | 331-335 |
| `tbody tr:hover` | typography | 1 props | 337-339 |
| `.frequency.high` | typography | 2 props | 342-345 |
| `.frequency.medium` | typography | 2 props | 347-350 |
| `.frequency.low` | typography | 2 props | 352-355 |
| `fieldset` | box_model | 4 props | 362-367 |
| `legend` | typography | 3 props | 369-373 |
| `.form-group` | box_model | 1 props | 376-378 |
| `label` | typography | 4 props | 381-386 |
| `.required` | typography | 1 props | 388-390 |
| `input[type="text"],
input[type="email"],` | box_model | 8 props | 393-413 |
| `input:focus,
textarea:focus,
select:focu` | box_model | 3 props | 415-421 |
| `input:invalid,
textarea:invalid,
select:` | box_model | 1 props | 423-427 |
| `::placeholder` | typography | 2 props | 430-433 |
| `textarea` | box_model | 2 props | 436-439 |
| `select` | background | 6 props | 442-449 |
| `.radio-group,
.checkbox-group` | layout | 3 props | 452-457 |
| `input[type="radio"],
input[type="checkbo` | box_model | 2 props | 459-463 |
| `input[type="range"]` | box_model | 6 props | 466-473 |
| `input[type="range"]::-webkit-slider-thum` | box_model | 7 props | 475-483 |
| `input[type="range"]::-moz-range-thumb` | box_model | 6 props | 485-492 |
| `input[type="file"]` | box_model | 4 props | 495-500 |
| `input[type="file"]:hover` | box_model | 1 props | 502-504 |
| `.btn` | typography | 13 props | 510-524 |
| `.btn:focus` | other | 2 props | 526-529 |
| `.btn:disabled` | other | 2 props | 531-534 |
| `.btn-primary` | typography | 3 props | 537-541 |
| `.btn-primary:hover` | typography | 2 props | 543-546 |
| `.btn-secondary` | typography | 3 props | 548-552 |
| `.btn-secondary:hover` | typography | 2 props | 554-557 |
| `.btn-success` | typography | 3 props | 559-563 |
| `.btn-danger` | typography | 3 props | 565-569 |
| `.btn-sm` | box_model | 2 props | 572-575 |
| `.btn-lg` | box_model | 2 props | 577-580 |
| `.container` | box_model | 4 props | 587-592 |
| `.grid` | layout | 2 props | 595-598 |
| `.grid-cols-1` | grid | 1 props | 600-602 |
| `.grid-cols-2` | grid | 1 props | 604-606 |
| `.grid-cols-3` | grid | 1 props | 608-610 |
| `.grid-cols-4` | grid | 1 props | 612-614 |
| `.flex` | layout | 1 props | 617-619 |
| `.flex-col` | flexbox | 1 props | 621-623 |
| `.flex-wrap` | flexbox | 1 props | 625-627 |
| `.items-center` | flexbox | 1 props | 629-631 |
| `.justify-center` | flexbox | 1 props | 633-635 |
| `.justify-between` | flexbox | 1 props | 637-639 |
| `.main-header` | layout | 5 props | 645-651 |
| `.navigation` | flexbox | 4 props | 653-658 |
| `.nav-brand h1` | box_model | 2 props | 660-663 |
| `.nav-brand a` | typography | 2 props | 665-668 |
| `.nav-menu` | box_model | 5 props | 670-676 |
| `.nav-link` | typography | 6 props | 678-685 |
| `.nav-link:hover` | typography | 2 props | 687-690 |
| `.menu-toggle` | box_model | 6 props | 693-700 |
| `.menu-toggle span` | box_model | 5 props | 702-708 |
| `.main-content` | box_model | 1 props | 714-716 |
| `.hero-section` | typography | 4 props | 719-724 |
| `.hero-title` | typography | 3 props | 726-730 |
| `.hero-subtitle` | box_model | 3 props | 732-736 |
| `.hero-actions` | flexbox | 4 props | 738-743 |
| `section` | box_model | 1 props | 746-748 |
| `section:nth-child(even)` | typography | 1 props | 750-752 |
| `.section-subtitle` | typography | 3 props | 754-758 |
| `.features-grid` | layout | 4 props | 761-766 |
| `.feature-card` | box_model | 5 props | 768-774 |
| `.feature-card:hover` | animation | 2 props | 776-779 |
| `.feature-card h3` | box_model | 2 props | 781-784 |
| `.lists-grid` | layout | 3 props | 787-791 |
| `.list-item` | box_model | 4 props | 793-798 |
| `.media-grid` | layout | 3 props | 801-805 |
| `.media-item` | typography | 1 props | 807-809 |
| `.media-item img,
.media-item video,
.med` | box_model | 3 props | 811-817 |
| `figcaption` | typography | 3 props | 819-823 |
| `.sidebar` | box_model | 4 props | 829-834 |
| `.widget` | box_model | 1 props | 836-838 |
| `.widget:last-child` | box_model | 1 props | 840-842 |
| `.widget h3` | box_model | 4 props | 844-849 |
| `.widget ul` | box_model | 2 props | 851-854 |
| `.widget li` | box_model | 1 props | 856-858 |
| `.news-item` | box_model | 4 props | 860-865 |
| `.news-item time` | typography | 3 props | 867-871 |
| `.main-footer` | box_model | 4 props | 877-882 |
| `.footer-content` | layout | 4 props | 884-889 |
| `.footer-section h4` | box_model | 2 props | 891-894 |
| `.footer-section ul` | box_model | 2 props | 896-899 |
| `.footer-section li` | box_model | 1 props | 901-903 |
| `.footer-section a` | typography | 3 props | 905-909 |
| `.footer-section a:hover` | typography | 1 props | 911-913 |
| `.footer-bottom` | box_model | 4 props | 915-920 |
| `.fade-in` | animation | 1 props | 938-940 |
| `.slide-in-left` | animation | 1 props | 954-956 |
| `.pulse` | animation | 1 props | 968-970 |
| `.spin` | animation | 1 props | 982-984 |
| `.bounce` | animation | 1 props | 1002-1004 |
| `.hidden` | layout | 1 props | 1011-1013 |
| `.visible` | layout | 1 props | 1015-1017 |
| `.invisible` | layout | 1 props | 1019-1021 |
| `.text-left` | typography | 1 props | 1024-1026 |
| `.text-center` | typography | 1 props | 1028-1030 |
| `.text-right` | typography | 1 props | 1032-1034 |
| `.text-justify` | typography | 1 props | 1036-1038 |
| `.text-primary` | typography | 1 props | 1041-1043 |
| `.text-secondary` | typography | 1 props | 1045-1047 |
| `.text-success` | typography | 1 props | 1049-1051 |
| `.text-danger` | typography | 1 props | 1053-1055 |
| `.text-warning` | typography | 1 props | 1057-1059 |
| `.text-info` | typography | 1 props | 1061-1063 |
| `.text-light` | typography | 1 props | 1065-1067 |
| `.text-dark` | typography | 1 props | 1069-1071 |
| `.text-white` | typography | 1 props | 1073-1075 |
| `.bg-primary` | typography | 1 props | 1078-1080 |
| `.bg-secondary` | typography | 1 props | 1082-1084 |
| `.bg-success` | typography | 1 props | 1086-1088 |
| `.bg-danger` | typography | 1 props | 1090-1092 |
| `.bg-warning` | typography | 1 props | 1094-1096 |
| `.bg-info` | typography | 1 props | 1098-1100 |
| `.bg-light` | typography | 1 props | 1102-1104 |
| `.bg-dark` | typography | 1 props | 1106-1108 |
| `.bg-white` | typography | 1 props | 1110-1112 |
| `.m-0` | box_model | 1 props | 1115-1115 |
| `.m-1` | box_model | 1 props | 1116-1116 |
| `.m-2` | box_model | 1 props | 1117-1117 |
| `.m-3` | box_model | 1 props | 1118-1118 |
| `.m-4` | box_model | 1 props | 1119-1119 |
| `.m-5` | box_model | 1 props | 1120-1120 |
| `.p-0` | box_model | 1 props | 1122-1122 |
| `.p-1` | box_model | 1 props | 1123-1123 |
| `.p-2` | box_model | 1 props | 1124-1124 |
| `.p-3` | box_model | 1 props | 1125-1125 |
| `.p-4` | box_model | 1 props | 1126-1126 |
| `.p-5` | box_model | 1 props | 1127-1127 |
| `.border` | box_model | 1 props | 1130-1132 |
| `.border-top` | box_model | 1 props | 1134-1136 |
| `.border-bottom` | box_model | 1 props | 1138-1140 |
| `.border-left` | box_model | 1 props | 1142-1144 |
| `.border-right` | box_model | 1 props | 1146-1148 |
| `.border-0` | box_model | 1 props | 1150-1152 |
| `.rounded` | box_model | 1 props | 1155-1157 |
| `.rounded-sm` | box_model | 1 props | 1159-1161 |
| `.rounded-lg` | box_model | 1 props | 1163-1165 |
| `.rounded-full` | box_model | 1 props | 1167-1169 |
| `.shadow` | other | 1 props | 1172-1174 |
| `.shadow-sm` | other | 1 props | 1176-1178 |
| `.shadow-lg` | other | 1 props | 1180-1182 |
| `.shadow-none` | other | 1 props | 1184-1186 |
| `.container` | box_model | 1 props | 1194-1196 |
| `.hero-title` | typography | 1 props | 1198-1200 |
| `.hero-subtitle` | typography | 1 props | 1202-1204 |
| `.hero-actions` | flexbox | 2 props | 1206-1209 |
| `.features-grid,
    .lists-grid,
    .me` | grid | 1 props | 1211-1215 |
| `.nav-menu` | layout | 9 props | 1217-1227 |
| `.nav-menu.active` | layout | 1 props | 1229-1231 |
| `.menu-toggle` | layout | 1 props | 1233-1235 |
| `.footer-content` | typography | 2 props | 1237-1240 |
| `table` | typography | 1 props | 1242-1244 |
| `th,
    td` | box_model | 1 props | 1246-1249 |
| `.features-grid` | grid | 1 props | 1254-1256 |
| `.lists-grid` | grid | 1 props | 1258-1260 |
| `.media-grid` | grid | 1 props | 1262-1264 |
| `.sidebar` | layout | 3 props | 1269-1273 |
| `.main-content` | layout | 4 props | 1275-1280 |
| `.container` | box_model | 1 props | 1285-1287 |
| `.features-grid` | grid | 1 props | 1289-1291 |
| `:root` | typography | 2 props | 1296-1299 |
| `body` | typography | 2 props | 1301-1304 |
| `.main-header` | typography | 1 props | 1306-1308 |
| `.feature-card,
    .list-item` | typography | 2 props | 1310-1314 |
| `table` | typography | 1 props | 1316-1318 |
| `th` | typography | 1 props | 1320-1322 |
| `input,
    textarea,
    select` | typography | 3 props | 1324-1330 |
| `.sidebar` | typography | 1 props | 1332-1334 |
| `.news-item` | typography | 1 props | 1336-1338 |
| `*` | typography | 4 props | 1343-1348 |
| `a,
    a:visited` | typography | 1 props | 1350-1353 |
| `a[href]:after` | other | 1 props | 1355-1357 |
| `abbr[title]:after` | other | 1 props | 1359-1361 |
| `.main-header,
    .sidebar,
    .main-fo` | layout | 1 props | 1363-1367 |
| `.main-content` | box_model | 3 props | 1369-1373 |
| `h1, h2, h3` | other | 1 props | 1375-1377 |
| `blockquote,
    tr,
    img` | other | 1 props | 1379-1383 |
| `p,
    h2,
    h3` | other | 2 props | 1385-1390 |
| `thead` | layout | 1 props | 1392-1394 |
| `:root` | typography | 6 props | 1399-1406 |
| `a` | typography | 1 props | 1408-1410 |
| `button,
    .btn` | box_model | 1 props | 1412-1415 |
| `*,
    *::before,
    *::after` | animation | 4 props | 1420-1427 |
| `.btn-primary` | typography | 1 props | 1435-1438 |
| `.text-primary` | typography | 1 props | 1440-1443 |
| `.feature-card,
.btn` | other | 1 props | 1450-1453 |
| `img` | box_model | 3 props | 1463-1467 |
| `html` | other | 1 props | 1470-1472 |
| `@supports (scroll-behavior: smooth) {
  ` | other | 0 props | 1474-1478 |
| `html` | other | 1 props | 1475-1477 |

## At-Rules

| Type | Name | Lines |
|------|------|-------|
| at-rule | `@keyframes` | 927-936 |
| at-rule | `@keyframes` | 943-952 |
| at-rule | `@keyframes` | 959-966 |
| at-rule | `@keyframes` | 973-980 |
| at-rule | `@keyframes` | 987-1000 |
| at-rule | `@media` | 1193-1250 |
| at-rule | `@media` | 1253-1265 |
| at-rule | `@media` | 1268-1281 |
| at-rule | `@media` | 1284-1292 |
| at-rule | `@media` | 1295-1339 |
| at-rule | `@media` | 1342-1395 |
| at-rule | `@media` | 1398-1416 |
| at-rule | `@media` | 1419-1428 |
| at-rule | `@font-face` | 1456-1460 |

## Top Properties

| Property | Usage Count |
|----------|-------------|
| color | 48 |
| background-color | 46 |
| padding | 39 |
| margin-bottom | 25 |
| font-size | 24 |
| display | 21 |
| border-radius | 21 |
| grid-template-columns | 15 |
| margin | 13 |
| font-weight | 13 |
