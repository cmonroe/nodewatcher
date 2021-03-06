from django import forms as django_forms

from . import base

__all__ = (
    'RemoveFormAction',
    'AppendFormAction',
    'AssignToFormAction',
)


class RegistryFormAction(object):
    """
    An abstract action that can modify lists of registry forms.
    """

    def modify_form(self, context, index, form_prefix):
        """
        Subclasses should provide action implementation in this method. It
        will be executed for each generated subform. In case it doesn't return
        None, the return value should be a render item that will be used instead
        of the default form. In this case the default form will not be generated.

        :param context: Form context
        :param index: Form index
        :param form_prefix: Form prefix string
        """

        pass

    def modify_forms_before(self, context):
        """
        Subclasses should provide action implementation in this method. It
        will be executed before the subforms are generated.

        :param context: Form context
        """

        pass

    def modify_forms_after(self, context):
        """
        Subclasses should provide action implementation in this method. It
        will be executed after the subforms are generated.

        :param context: Form context
        """

        pass


class RemoveFormAction(RegistryFormAction):
    """
    An action that removes forms specified by index.
    """

    def __init__(self, indices, parent=None):
        """
        Class constructor.

        :param indices: Form indices to remove
        :param parent: Optional partial parent item
        """

        self.indices = sorted(indices)
        self.parent = parent

    def modify_forms_before(self, context):
        """
        Removes specified subforms.
        """

        if self.parent != context.hierarchy_parent_current or len(self.indices) < 1:
            return False

        # Move form data as forms might be renumbered
        form_prefix = context.base_prefix + '_mu_'
        reduce_by = 0
        for i in xrange(context.user_form_count):
            if i in self.indices:
                for key in context.data.keys():
                    if key.startswith(form_prefix + str(i) + '_') or key.startswith(form_prefix + str(i) + '-'):
                        del context.data[key]

                reduce_by += 1
                continue
            elif not reduce_by:
                continue

            for key in context.data.keys():
                postfix = None
                if key.startswith(form_prefix + str(i) + '_'):
                    postfix = '_'
                elif key.startswith(form_prefix + str(i) + '-'):
                    postfix = '-'

                if postfix is not None:
                    new_key = key.replace(form_prefix + str(i) + postfix, form_prefix + str(i - reduce_by) + postfix)
                    context.data[new_key] = context.data[key]
                    del context.data[key]

        # Reduce form count depending on how many forms have been removed
        context.user_form_count -= len(self.indices)
        return True


class AppendFormAction(RegistryFormAction):
    """
    An action that appends a new form at the end of current subforms.
    """

    def __init__(self, item, parent=None):
        """
        Class constructor.

        :param item: Configuration item that should be appended
        :param parent: Optional partial parent item
        """

        self.item = item
        self.parent = parent

    def modify_forms_after(self, context):
        """
        Appends a new form at the end of current subforms.
        """

        if self.parent != context.hierarchy_parent_current:
            return False

        form_prefix = context.base_prefix + '_mu_' + str(len(context.subforms))
        item = self.item
        if item is None:
            item = context.form_state.create_item(
                context.default_item_cls,
                {},
                parent=context.hierarchy_parent_current,
            )

        context.subforms.append(base.generate_form_for_class(
            context,
            form_prefix,
            None,
            len(context.subforms),
            instance=item,
            force_selector_widget=context.force_selector_widget,
        ))

        return True


class AssignToFormAction(RegistryFormAction):
    """
    An action that assigns to an existing form.
    """

    def __init__(self, item, index, fields, parent=None):
        """
        Class constructor.

        :param item: Configuration item
        :param index: Subform index
        :param fields: A list of fields to assign
        :param parent: Optional partial parent item
        """

        self.item = item
        self.index = index
        self.fields = fields
        self.parent = parent

    def modify_form(self, context, index, form_prefix):
        """
        Assigns to an existing form.
        """

        if self.parent != context.hierarchy_parent_current:
            return

        if self.index != index:
            return

        # Modify any overriden values.
        data = django_forms.model_to_dict(self.item)
        for field in self.fields:
            values = data[field]
            if not isinstance(values, (list, tuple)):
                # We need to support updates of lists of values.
                values = [values]

            field_name = context.get_prefix(form_prefix, self.item, field)
            for value in values:
                context.data.update({field_name: value})
