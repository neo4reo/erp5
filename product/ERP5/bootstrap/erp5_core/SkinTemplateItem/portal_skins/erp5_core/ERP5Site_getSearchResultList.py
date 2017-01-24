# Use getDocumentValueList for ERP5 Web
if context.getWebSectionValue() is None:
  search_method = context.getPortalObject().portal_catalog
else:
  search_method = context.getDocumentValueList
return search_method(**kw)
