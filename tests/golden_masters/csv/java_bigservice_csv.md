Type,Name,Signature,Visibility,Lines,Complexity,Doc
Field,DEFAULT_ENCODING,DEFAULT_ENCODING:String,private,19-19,,-
Field,MAX_RETRY_COUNT,MAX_RETRY_COUNT:int,private,20-20,,-
Field,TIMEOUT_MILLISECONDS,TIMEOUT_MILLISECONDS:long,private,21-21,,-
Field,DATE_FORMAT,DATE_FORMAT:String,private,22-22,,-
Field,dataSource,dataSource:DataSource,private,24-24,,-
Field,configurationCache,"configurationCache:Map<String, Object>",private,25-25,,-
Field,activeConnections,activeConnections:List<String>,private,26-26,,-
Field,validatedUsers,validatedUsers:Set<String>,private,27-27,,-
Field,pendingOperations,pendingOperations:Queue<String>,private,28-28,,-
Constructor,BigService,():void,public,33-39,1,-
Method,initializeService,():void,private,44-50,1,-
Method,loadConfiguration,():void,private,55-65,2,-
Method,setupDatabaseConnection,():void,private,70-77,2,-
Method,validateSystemRequirements,():void,private,82-88,1,-
Method,checkMemoryUsage,():void,private,93-106,2,-
Method,checkDiskSpace,():void,private,111-117,2,-
Method,checkNetworkConnectivity,():void,private,122-136,3,-
Method,authenticateUser,"(username:String, password:String):boolean",public,141-172,6,-
Method,createSession,(username:String):String,public,177-199,5,-
Method,validateData,"(data:Map<String, Object>):boolean",public,204-246,10,-
Method,validateEmail,(email:String):boolean,private,251-254,1,-
Method,validatePhoneNumber,(phone:String):boolean,private,259-262,1,-
Method,validateDate,(date:String):boolean,private,267-275,2,-
Method,logOperation,"(operation:String, details:String):void",public,280-290,2,-
Method,manageCache,"(key:String, value:Object):void",public,295-308,2,-
Method,cleanupCache,():void,private,313-326,2,-
Method,updateCacheStatistics,():void,private,331-335,1,-
Method,calculateCacheHitRatio,():double,private,340-343,1,-
Method,performBackup,(backupType:String):void,public,348-367,1,-
Method,performFullBackup,():void,private,372-395,6,-
Method,performIncrementalBackup,():void,private,400-414,4,-
Method,performDifferentialBackup,():void,private,419-433,4,-
Method,generateReport,"(reportType:String, parameters:Map<String, Object>):void",public,438-471,2,-
Method,prepareReportData,"(reportType:String, parameters:Map<String, Object>):void",private,476-490,4,-
Method,generateSalesReport,"(parameters:Map<String, Object>):void",private,495-513,6,-
Method,generatePerformanceReport,"(parameters:Map<String, Object>):void",private,518-534,5,-
Method,generateUserActivityReport,"(parameters:Map<String, Object>):void",private,539-553,4,-
Method,generateSystemHealthReport,"(parameters:Map<String, Object>):void",private,558-574,5,-
Method,finalizeReport,(reportType:String):void,private,579-593,4,-
Method,updateCustomerName,"(customerId:String, newName:String):void",public,601-617,4,-
Method,getCustomerInfo,"(customerId:String):Map<String, Object>",public,622-652,5,-
Method,deleteCustomer,(customerId:String):boolean,public,657-691,9,-
Method,processOrder,"(customerId:String, items:List<String>, totalAmount:double):String",public,696-736,10,-
Method,manageInventory,"(action:String, itemId:String, quantity:int):void",public,741-773,3,-
Method,addInventory,"(itemId:String, quantity:int):void",private,778-792,4,-
Method,removeInventory,"(itemId:String, quantity:int):void",private,797-811,4,-
Method,updateInventory,"(itemId:String, quantity:int):void",private,816-830,4,-
Method,checkInventory,(itemId:String):void,private,835-850,4,-
Method,sendNotification,"(recipient:String, message:String, type:String):void",public,855-884,7,-
Method,shutdownSystem,():void,public,889-912,6,-
Method,savePendingOperations,():void,private,917-926,2,-
Method,closeDatabaseConnections,():void,private,931-940,2,-
Method,finalizeSystemLogs,():void,private,945-953,2,-
Method,handleError,"(error:Exception, context:String):void",public,958-977,4,-
Method,handleDatabaseError,(error:SQLException):void,private,982-996,4,-
Method,handleValidationError,(error:IllegalArgumentException):void,private,1001-1009,2,-
Method,handleRuntimeError,(error:RuntimeException):void,private,1014-1028,4,-
Method,handleGenericError,(error:Exception):void,private,1033-1041,2,-
Method,monitorPerformance,():void,public,1046-1067,1,-
Method,monitorCpuUsage,():void,private,1072-1086,3,-
Method,monitorMemoryUsage,():void,private,1091-1112,3,-
Method,monitorDiskIO,():void,private,1117-1131,2,-
Method,monitorNetworkUsage,():void,private,1136-1150,2,-
Method,performSecurityCheck,():void,public,1155-1171,1,-
Method,checkAccessPermissions,():void,private,1176-1192,5,-
Method,validateSecuritySettings,():void,private,1197-1211,4,-
Method,performVulnerabilityScan,():void,private,1216-1230,4,-
Method,reviewSecurityLogs,():void,private,1235-1249,4,-
Method,synchronizeData,"(sourceSystem:String, targetSystem:String):void",public,1254-1283,3,-
Method,prepareSynchronization,"(sourceSystem:String, targetSystem:String):void",private,1288-1302,4,-
Method,extractData,(sourceSystem:String):void,private,1307-1323,5,-
Method,transformData,():void,private,1328-1342,4,-
Method,loadData,(targetSystem:String):void,private,1347-1361,4,-
Method,verifySynchronization,"(sourceSystem:String, targetSystem:String):void",private,1366-1380,4,-
Method,main,(args:String[]):void [static],public,1385-1418,1,-
