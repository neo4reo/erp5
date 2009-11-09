# -*- coding: utf-8 -*-
##############################################################################
#
# Copyright (c) 2009 Nexedi SA and Contributors. All Rights Reserved.
#                    Jean-Paul Smets-Solanes <jp@nexedi.com>
#
# WARNING: This program as such is intended to be used by professional
# programmers who take the whole responsability of assessing all potential
# consequences resulting from its eventual inadequacies and bugs
# End users who are looking for a ready-to-use solution with commercial
# garantees and support are strongly adviced to contract a Free Software
# Service Company
#
# This program is Free Software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.
#
##############################################################################

import zope.interface

from Products.CMFCore.utils import getToolByName

from AccessControl import ClassSecurityInfo
from Globals import InitializeClass, DTMLFile
from Products.ERP5Type import Permissions, interfaces
from Products.ERP5Type.Tool.BaseTool import BaseTool
from Products.ERP5Type.Message import translateString
from Products.ERP5 import DeliverySolver

from Products.ERP5 import _dtmldir

from zLOG import LOG

class SolverTool(BaseTool):
  """
    The SolverTool provides API to find out which solver can
    be applied in which case and contains SolverProcess instances
    which are used to keep track of solver decisions, solver
    history and global optimisation.

    NOTE: this class is experimental and is subject to be removed
  """
  id = 'portal_solvers'
  meta_type = 'ERP5 Solver Tool'
  portal_type = 'Solver Tool'
  allowed_types = ( 'ERP5 Solver Process', )

  # Declarative Security
  security = ClassSecurityInfo()

  #
  #   ZMI methods
  #
  security.declareProtected( Permissions.ManagePortal, 'manage_overview' )
  manage_overview = DTMLFile( 'explainSolverTool', _dtmldir )

  # Declarative interfaces
  zope.interface.implements(interfaces.IDeliverySolverFactory,
                            interfaces.IDivergenceController,
                           )

  # Implementation
  def filtered_meta_types(self, user=None):
    # Filters the list of available meta types.
    all = SolverTool.inheritedAttribute('filtered_meta_types')(self)
    meta_types = []
    for meta_type in self.all_meta_types():
      if meta_type['name'] in self.allowed_types:
        meta_types.append(meta_type)
    return meta_types

  def tpValues(self) :
    """ show the content in the left pane of the ZMI """
    return self.objectValues()

  # IDeliverySolverFactory implementation
  def newDeliverySolver(self, class_name, movement_list):
    """
    """
    raise NotImplementedError

  def getDeliverySolverClassNameList(self):
    """
    """
    # XXX Hardcoded for now. We need a new registration system for
    # delivery solvers.
    return ['FIFO', 'FILO', 'MinPrice',]

  def getDeliverySolverTranslatedItemList(self, class_name_list=None):
    """
    """
    return sorted([(self.getDeliverySolverTranslatedTitle(x), x) \
                   for x in self.getDeliverySolverClassNameList() \
                   if class_name_list is None or x in class_name_list],
                  key=lambda x:str(x[0]))

  def getDeliverySolverTranslatedTitle(self, class_name):
    """
    """
    __import__('%s.%s' % (DeliverySolver.__name__, class_name))
    return translateString(
      getattr(getattr(DeliverySolver, class_name), class_name).title)

  def getDeliverySolverTranslatedDescription(self, class_name):
    """
    """
    __import__('%s.%s' % (DeliverySolver.__name__, class_name))
    return translateString(
      getattr(getattr(DeliverySolver, class_name), class_name).__doc__)

  # IDivergenceController implementation
  def isDivergent(self, delivery_or_movement=None):
    """
    Returns True if any of the movements provided 
    in delivery_or_movement is divergent

    delivery_or_movement -- a movement, a delivery, 
                            or a list thereof
    """

  def newSolverProcess(self, delivery_or_movement=None):
    """
    Builds a new solver process from the divergence
    analaysis of delivery_or_movement. All movements
    which are not divergence are placed in a Solver
    Decision with no Divergence Tester specified.

    delivery_or_movement -- a movement, a delivery, 
                            or a list thereof
    """
    # Do not create a new solver process if no divergence
    if not self.isDivergent(delivery_or_movement=delivery_or_movement):
      return None

    # We suppose here that delivery_or_movement is a list of
    # delivery lines. Let group decisions in such way
    # that a single decision is created per divergence tester instance
    # and per application level list
    solver_decision_dict = {}
    for movement in delivery_or_movement:
      for simulation_movement in movement.getDeliveryRelatedValueList():
        simulation_movemet_url = simulation_movement.getRelativeUrl()
        for divergence_tester in simulation_movement.getParentValue().getDivergenceTesterValueList():
          application_list = map(lambda x:x.getRelativeUrl(), 
                 self.getSolverDecisionApplicationValueList(simulation_movement, divergence_tester))
          application_list.sort()
          solver_decision_key = (divergence_tester.getRelativeUrl(), application_list)
          movement_dict = solver_decision_dict.setdefaults(solver_decision_key, {})
          movement_dict[simulation_movemet_url] = None

    # Now build the solver process instances based on the previous
    # grouping
    new_solver = self.newContent(portal_type='Solver Process')
    for solver_decision_key, movement_dict in solver_decision_dict.items():
      new_decision = self.newContent(portal_type='Solver Decision')
      new_decision._setDeliveryList(movement_dict.keys())
      new_decision._setSolver(solver_decision_key[0])
      # No need to set application_list or....?

  def getSolverProcessValueList(self, delivery_or_movement=None, validation_state=None):
    """
    Returns the list of solver processes which are
    are in a given state and which apply to delivery_or_movement.
    This method is useful to find applicable solver processes
    for a delivery.

    delivery_or_movement -- a movement, a delivery, 
                            or a list thereof

    validation_state -- a state of a list of states
                        to filter the result
    """

  def getSolverDecisionValueList(self, delivery_or_movement=None, validation_state=None):
    """
    Returns the list of solver decisions which apply
    to a given movement.

    delivery_or_movement -- a movement, a simulation movement, a delivery, 
                            or a list thereof

    validation_state -- a state of a list of states
                        to filter the result
    """

  def getSolverDecisionApplicationValueList(self, movement, divergence_tester=None):
    """
    Returns the list of documents at which a given divergence resolution
    can be resolved at. For example, in most cases, date divergences can
    only be resolved at delivery level whereas quantities are usually
    resolved at cell level.

    The result of this method is a list of ERP5 documents.

    NOTE: renaming probably required. I do not like this name nor the one
    of the interface definition.
    """
    # Short Term Implementation Approach
    return self.SolverTool_getSolverDecisionApplicationValueList(movement, divergence_tester)

    # Alternate short Term Implementation Approach
    return divergence_tester.getTypeBasedMethod('getSolverDecisionApplicationValueList')( 
                                                movement, divergence_tester)

    # Alternate short Term Implementation Approach
    test_property = divergence_tester.getTestedProperty()
    application_value = movement
    while not application_value.hasProperty(test_property):
      application_value = application_value.getParentValue()
    return application_value

    # Mid-term implementation (we suppose movement is a delivery)
    # use delivery builders to find out at which level the given
    # property can be modified
    test_property = divergence_tester.getTestedProperty()
    application_value_level = {}
    for simulation_movement in movement.getDeliveryRelatedValueList():
      business_path = simulation_movement.getCausalityValue()
      for delivery_builder in business_path.getDeliveryBuilderValueList():
        for movement_group in delivery_builder.contentValues(): # filter missing
          if test_property in movement_group.getTestedPropertyList():
            application_value_level[movement_group.getCollectGroupOrder()] = None
    result = []
    # Delivery level
    if 'delivery' in application_value_level:
      result.append(movement.getDeliveryValue())
    # Line level
    if 'line' in application_value_level and not movement.isLine():
      result.append(movement)
    elif 'line' in application_value_level and not movement.isLine():
      result.append(movement.getParentValue())
    # Cell level
    if 'cell' in application_value_level and movement.isCell():
      result.append(movement)
    # Group of lines level (we try to find the most appropriate enclosing group)
    if 'group' in application_value_level:
      application_value = movement
      while not application_value.hasProperty(test_property):
        application_value = application_value.getParentValue()
      if application_value not in result: result.append(application_value)
    # Group of lines level (we try to find the most appropriate enclosing group)
    if 'all_group' in application_value_level:
      application_value = movement
      while not application_value.hasProperty(test_property):
        application_value = application_value.getParentValue()
        if application_value not in result: result.append(application_value)
    return result

    # Longer-term implementation (we suppose movement is a delivery)
    # use delivery builders to find out at which level the given
    # property can be modified
    test_property = divergence_tester.getTestedProperty()
    application_value_level = {}
    for simulation_movement in movement.getDeliveryRelatedValueList():
      business_path = simulation_movement.getCausalityValue()
      for delivery_builder in business_path.getDeliveryBuilderValueList():
        for property_group in delivery_builder.contentValues(portal_type="Property group"):
          if test_property in property_group.getTestedPropertyList():
            application_value_level[property_group.getCollectGroupOrder()] = None
    # etc. same
