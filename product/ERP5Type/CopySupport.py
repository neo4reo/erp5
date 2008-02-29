##############################################################################
#
# Copyright (c) 2002 Nexedi SARL. All Rights Reserved.
# Copyright (c) 2001 Zope Corporation and Contributors. All Rights Reserved.
#
# This software is subject to the provisions of the Zope Public License,
# Version 2.0 (ZPL).  A copy of the ZPL should accompany this distribution.
# THIS SOFTWARE IS PROVIDED "AS IS" AND ANY AND ALL EXPRESS OR IMPLIED
# WARRANTIES ARE DISCLAIMED, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF TITLE, MERCHANTABILITY, AGAINST INFRINGEMENT, AND FITNESS
# FOR A PARTICULAR PURPOSE
#
##############################################################################

from OFS import Moniker
from AccessControl import ClassSecurityInfo, getSecurityManager
from AccessControl.Permission import Permission
from OFS.ObjectManager import ObjectManager
from OFS.CopySupport import CopyContainer as OriginalCopyContainer
from OFS.CopySupport import CopyError
from OFS.CopySupport import eNotSupported, eNoItemsSpecified
from OFS.CopySupport import _cb_encode, _cb_decode, cookie_path
from Products.ERP5Type import Permissions
from Acquisition import aq_base
from Products.CMFCore.utils import getToolByName
from Globals import PersistentMapping, MessageDialog
from Products.ERP5Type.Utils import get_request
from Products.CMFCore.WorkflowCore import WorkflowException
from Products.CMFCore.CatalogTool import CatalogTool as CMFCoreCatalogTool
from Products.CMFActivity.Errors import ActivityPendingError

_marker = object()

from zLOG import LOG

class CopyContainer:
  """This class redefines the copy/paste methods  which are required in ERP5 in
  relation with the ZSQLCatalog and CMFCategory. Class using class should also
  inherit from ERP5Type.Base 

    It is used as a mix-in to patch the default Zope behaviour

    It should be moved to the ZSQL Catalog sooner or later

    PLAIN UGGLY CODE: it should also be cleaned up in a way that reuses
    better the existing classes rather than copy/pasting the code
  """

  # Declarative security
  security = ClassSecurityInfo()
  
  # Copy / Paste support
  security.declareProtected( Permissions.AccessContentsInformation, 'manage_copyObjects' )
  def manage_copyObjects(self, ids=None, uids=None, REQUEST=None, RESPONSE=None):
      """
        Put a reference to the objects named in ids in the clip board
      """
      #LOG("Manage Copy",0, "ids:%s uids:%s" % (str(ids), str(uids)))
      if ids is not None:
        # Use default methode
        return OriginalCopyContainer.manage_copyObjects(self, ids, REQUEST,
            RESPONSE)
      if uids is None and REQUEST is not None:
          return eNoItemsSpecified
      elif uids is None:
          raise ValueError, 'uids must be specified'

      if isinstance(uids, (str, int)):
          ids=[uids]
      oblist=[]
      for uid in uids:
          ob=self.portal_catalog.getObject(uid)
          if not ob.cb_isCopyable():
              raise CopyError, eNotSupported % uid
          m=Moniker.Moniker(ob)
          oblist.append(m.dump())
      cp=(0, oblist)
      cp=_cb_encode(cp)
      if REQUEST is not None:
          resp=REQUEST['RESPONSE']
          resp.setCookie('__cp', cp, path='%s' % cookie_path(REQUEST))
          REQUEST['__cp'] = cp
          return self.manage_main(self, REQUEST)
      return cp

  def _updateInternalRelatedContent(self, object, path_item_list, new_id):
      """
       Search for categories starting with path_item_list in object and its
       subobjects, and replace the last item of path_item_list by new_id
       in matching category path.

       object
         Object to recursively check in.
       path_item_list
         Path to search for.
         Should correspond to path_item_list when the function is initially
         called - but remains identical among all recursion levels under the
         same call.
       new_id
         Id replacing the last item in path_item_list.

       Example :
        previous category value : 'a/b/c/d/e'
        path_item_list : ['a', 'b', 'c']
        new_id : 'z'
        final category value    : 'a/b/z/d/e'
      """
      for subobject in object.objectValues():
          self._updateInternalRelatedContent(object=subobject,
                                             path_item_list=path_item_list,
                                             new_id=new_id)
      changed = 0
      category_list = object.getCategoryList()
      path_len = len(path_item_list)
      for position in xrange(len(category_list)):
          category_name = category_list[position].split('/')
          if category_name[1:path_len + 1] == path_item_list: # XXX Should be possible to do this in a cleaner way
              category_name[path_len] = new_id
              category_list[position] = '/'.join(category_name)
              changed = 1
      if changed != 0:
          object.setCategoryList(category_list)

  def _recursiveSetActivityAfterTag(self, obj, activate_kw=None):
      """
      Make sure to set an after tag on each object
      so that it is possible to unindex before doing
      indexing, this prevent uid changes
      """
      uid = getattr(aq_base(obj), 'uid', None)
      if uid is not None:
        if activate_kw is None:
          activate_kw = obj.getDefaultActivateParameterDict()
        try:
          activate_kw["after_tag"] = str(uid)
        except TypeError:
          activate_kw = {"after_tag":str(uid),}
        obj.setDefaultActivateParameters(**activate_kw)
      for sub_obj in obj.objectValues():
        self._recursiveSetActivityAfterTag(sub_obj, activate_kw)

  security.declareProtected( Permissions.ModifyPortalContent, 'manage_renameObject' )
  def manage_renameObject(self, id=None, new_id=None, REQUEST=None):
      """manage renaming an object while keeping coherency for contained
      and linked to objects inside the renamed object

      """
      ob = self._getOb(id)
      # Make sure there is no activities pending on that object
      try:
        portal_activities = getToolByName(self, 'portal_activities')
      except AttributeError:
        # There is no activity tool
        portal_activities = None
      if portal_activities is not None:
        if portal_activities.countMessage(path=ob.getPath())>0:
          raise ActivityPendingError, 'Sorry, pending activities prevent ' \
                         +  'changing id at this current stage'

      # Search for categories that have to be updated in sub objects.
      self._recursiveSetActivityAfterTag(ob)
      self._updateInternalRelatedContent(object=ob,
                                         path_item_list=ob.getRelativeUrl().split("/"),
                                         new_id=new_id)
      #ob._v_is_renamed = 1
      # Rename the object
      return OriginalCopyContainer.manage_renameObject(self, id=id, new_id=new_id, REQUEST=REQUEST)

  security.declareProtected( Permissions.DeletePortalContent, 'manage_cutObjects' )
  def manage_cutObjects(self, ids=None, uids=None, REQUEST=None, RESPONSE=None):
      """ manage cutting objects, ie objects will be copied ans deleted

      """
      #LOG("Manage Copy",0, "ids:%s uids:%s" % (str(ids), str(uids)))
      if ids is not None:
        # Use default methode
        return OriginalCopyContainer.manage_cutObjects(self, ids, REQUEST)
      if uids is None and REQUEST is not None:
          return eNoItemsSpecified
      elif uids is None:
          raise ValueError, 'uids must be specified'

      if isinstance(uids, (str, int)):
          ids=[uids]
      oblist=[]
      for uid in uids:
          ob=self.portal_catalog.getObject(uid)
          if not ob.cb_isMoveable():
              raise CopyError, eNotSupported % id
          m=Moniker.Moniker(ob)
          oblist.append(m.dump())
      cp=(1, oblist) # 0->1 This is the difference with manage_copyObject
      cp=_cb_encode(cp)
      if REQUEST is not None:
          resp=REQUEST['RESPONSE']
          resp.setCookie('__cp', cp, path='%s' % cookie_path(REQUEST))
          REQUEST['__cp'] = cp
          return self.manage_main(self, REQUEST)
      return cp


  security.declareProtected( Permissions.DeletePortalContent, 'manage_delObjects' )
  def manage_delObjects(self, ids=None, uids=None, REQUEST=None):
      """Delete a subordinate object

      The objects specified in 'ids' get deleted.
      """
      if ids is None: ids = []
      if uids is None: uids = []
      if len(ids) > 0:
        # Use default method
        return ObjectManager.manage_delObjects(self, ids, REQUEST)
      if isinstance(uids, (str, int)):
        ids=[uids]
      if not uids:
          return MessageDialog(title='No items specified',
                 message='No items were specified!',
                 action ='./manage_main',)
      while uids:
          uid=uids[-1]
          ob=self.portal_catalog.getObject(uid)
          container = ob.aq_inner.aq_parent
          id = ob.id
          v=container._getOb(id, self)
          if v is self:
              raise 'BadRequest', '%s does not exist' % ids[-1]
          container._delObject(id)
          del uids[-1]
      if REQUEST is not None:
              return self.manage_main(self, REQUEST, update_menu=1)

  # Copy and paste support
  def manage_afterClone(self, item):
    """
        Add self to the workflow.
        (Called when the object is cloned.)
    """
    #LOG("After Clone ",0, "id:%s containes:%s" % (str(item.id), str(container.id)))
    # Change uid attribute so that Catalog thinks object was not yet catalogued
    self_base = aq_base(self)
    #LOG("After Clone ",0, "self:%s item:%s" % (repr(self), repr(item)))
    #LOG("After Clone ",0, "self:%s item:%s" % (repr(self), repr(self.getPortalObject().objectIds())))
    portal_catalog = getToolByName(self, 'portal_catalog')
    self_base.uid = portal_catalog.newUid()

    # Give the Owner local role to the current user, zope only does this if no
    # local role has been defined on the object, which breaks ERP5Security
    if getattr(self_base, '__ac_local_roles__', None) is not None:
      user=getSecurityManager().getUser()
      if user is not None:
        userid=user.getId()
        if userid is not None:
          #remove previous owners
          dict = self.__ac_local_roles__
          for key, value in dict.items():
            if 'Owner' in value:
              value.remove('Owner')
          #add new owner
          l=dict.setdefault(userid, [])
          l.append('Owner')

    # Clear the transaction references
    if getattr(self_base, 'default_source_reference', None):
      delattr(self_base, 'default_source_reference')
    if getattr(self_base, 'default_destination_reference', None):
      delattr(self_base, 'default_destination_reference')
    
    # Clear the workflow history
    # XXX This need to be tested again
    if getattr(self_base, 'workflow_history', _marker) is not _marker:
      self_base.workflow_history = PersistentMapping()

    # Pass - need to find a way to pass calls...
    self.notifyWorkflowCreated()

    # Add info about copy to edit workflow
    REQUEST = get_request()
    pw = getToolByName(self, 'portal_workflow')
    if 'edit_workflow' in pw.getChainFor(self):
      if REQUEST is not None and REQUEST.get('__cp', None) :
        copied_item_list = _cb_decode(REQUEST['__cp'])[1]
        # Guess source item
        for c_item in copied_item_list:
          if c_item[-1] in item.getId():
            source_item = '/'.join(c_item)
            break
        else:
          source_item = '/'.join(copied_item_list[0])
        try:
          pw.doActionFor(self, 'edit_action', wf_id='edit_workflow', comment='Object copied from %s' % source_item)
        except WorkflowException:
          pass
      else:
        try:
          pw.doActionFor(self, 'edit_action', wf_id='edit_workflow', comment='Object copied as %s' % item.getId())
        except WorkflowException:
          pass

    ### Don't call makeTemplate here!!
    ### At this point, uid of sub object is still old and
    ### if calling makeTemplate, original document will be unindexed.

    # Call a type based method to reset so properties if necessary
    script = self._getTypeBasedMethod('afterClone')
    if script is not None and callable(script):
      script()

    self.__recurse('manage_afterClone', item)

  def manage_afterAdd(self, item, container):
      """
          Add self to the catalog.
          (Called when the object is created or moved.)
      """
      if aq_base(container) is not aq_base(self):
          #LOG("After Add ",0, "id:%s containes:%s" % (str(item.id), str(container.id)))
          if getattr(self, 'isIndexable', 0):
            self.reindexObject()
          if getattr(self, 'isIndexable', 1):
            self.__recurse('manage_afterAdd', item, container)

  def manage_beforeDelete(self, item, container):
      """
          Remove self from the catalog.
          (Called when the object is deleted or moved.)
      """
      if aq_base(container) is not aq_base(self):
          self.__recurse('manage_beforeDelete', item, container)
          if self.isIndexable:
            self.unindexObject()

  def __recurse(self, name, *args):
      """
          Recurse in both normal and opaque subobjects.
      """
      values = self.objectValues()
      opaque_values = self.opaqueValues()
      for subobjects in values, opaque_values:
          for ob in subobjects:
              s = getattr(ob, '_p_changed', 0)
              if getattr(aq_base(ob), name, _marker) is not _marker:
                getattr(ob, name)(*args)
              if s is None: ob._p_deactivate()

  security.declareProtected(Permissions.ModifyPortalContent, 'unindexObject')
  def unindexObject(self, path=None):
      """
          Unindex the object from the portal catalog.
      """
      if self.isIndexable:
        catalog = getToolByName(self, 'portal_catalog', None)
        if catalog is not None:
          # Make sure there is not activity for this object
          self.flushActivity(invoke=0)
          uid = getattr(self,'uid',None)
          if uid is None:
            return
          # Set the path as deleted, sql wich generate no locks
          # Set also many columns in order to make sure lines
          # marked as deleted will not be selected
          catalog.beforeUnindexObject(None,path=path,uid=uid)
          # Then start activty in order to remove lines in catalog,
          # sql wich generate locks
          catalog.activate(activity='SQLQueue',
                           tag='%s' % uid).unindexObject(None, 
                                           path=path,uid=uid)

  security.declareProtected(Permissions.ModifyPortalContent, 'moveObject')
  def moveObject(self, idxs=None):
      """
          Reindex the object in the portal catalog.
          If idxs is present, only those indexes are reindexed.
          The metadata is always updated.

          Also update the modification date of the object,
          unless specific indexes were requested.

          Passes is_object_moved to catalog to force
          reindexing without creating new uid
      """
      if idxs is None: idxs = []
      if idxs == []:
          # Update the modification date.
          if getattr(aq_base(self), 'notifyModified', _marker) is not _marker:
              self.notifyModified()
      catalog = getToolByName(self, 'portal_catalog', None)
      if catalog is not None:
          catalog.moveObject(self, idxs=idxs)

  def _notifyOfCopyTo(self, container, op=0):
      """Overiden to track object cut and pastes, and update related
      content accordingly.
      The op variable is 0 for a copy, 1 for a move.
      """
      if op == 1: # move
          self._v_category_url_before_move = self.getRelativeUrl()
          self._recursiveSetActivityAfterTag(self)

  def _setId(self, id):
    # Called to set the new id of a copied object.
    # XXX It is bad to use volatile attribute, because we may have naming 
    # conflict later.
    # Currently, it is required to use this volatile attribute
    # when we do a copy/paste, in order to change the relation in _postCopy.
    # Such implementation is due to the limitation of CopySuport API, which prevent
    # to pass parameter to manage_afterClone.
    self._v_previous_id = self.id
    self.id=id

  def _postCopy(self, container, op=0):
    # Called after the copy is finished to accomodate special cases.
    # The op var is 0 for a copy, 1 for a move.
    if op == 1:
      # In our case, we want to notify the category system that our path
      # changed, so that it updates related objects. 
      old_url = getattr(self, '_v_category_url_before_move', None)
      if old_url is not None:
          self.activate(after_method_id='unindexObject').updateRelatedContent(
                                old_url,
                                self.getRelativeUrl())
    elif op == 0:
      # Paste a object.
      # Update related subcontent
      previous_path = self.getRelativeUrl().split('/')
      previous_path[-1] = self._v_previous_id
      
      self._updateInternalRelatedContent(object=self, 
                                         path_item_list=previous_path, 
                                         new_id=self.id)

#### Helper methods

def tryMethodCallWithTemporaryPermission(context, permission, method,
    method_argv, method_kw, exception):
  # we want to catch the explicit security check done in manage_renameObject
  # and bypass it. for this, we temporarily give the Copy or Move right to the
  # user. We assume that if the user has enough rights to pass the
  # "declareProtected" check around "setId", he should be really able to
  # rename the object.
  try:
    return method(*method_argv, **method_kw)
  except exception:
    user = getSecurityManager().getUser()
    user_role_list = user.getRolesInContext(context)
    if len(user_role_list) > 0:
      perm_list = context.ac_inherited_permissions()
      for p in perm_list:
        if p[0] == permission:
          name, value = p[:2]
          break
      else:
        name, value = (permission, ())
      p = Permission(name,value,context)
      old_role_list = p.getRoles(default=[])
      p.setRoles(user_role_list)
      result = method(*method_argv, **method_kw)
      p.setRoles(old_role_list)
      return result

