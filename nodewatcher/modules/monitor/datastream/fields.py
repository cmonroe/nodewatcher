import collections

from django.core import exceptions

from datastream import exceptions as ds_exceptions
from django_datastream import datastream

from .pool import pool


class TagReference(object):
    """
    A reference to a tag that is dynamically generated by the streams
    descriptor in method get_stream_tags.
    """

    def __init__(self, tag_name):
        """
        Class constructor.

        :param tag_name: Name of the referenced tag
        """

        self.tag_name = tag_name

    def resolve(self, descriptor):
        """
        Resolves this field reference into an actual value.

        :param descriptor: Streams descriptor
        :return: Value of the referenced field
        """

        return reduce(lambda x, y: x[y], self.tag_name.split('.'), descriptor.get_stream_tags())


class Field(object):
    """
    A datastream Field contains metadata on how to extract datapoints and create
    streams from them. Values are then appended to these streams via the datastream
    API.
    """

    def __init__(self, attribute=None, tags=None):
        """
        Class constructor.

        :param attribute: Optional name of the attribute that is source of data for
          this field
        :param tags: Optional custom tags
        """

        self.name = None
        self.attribute = attribute
        self.custom_tags = tags or {}

    def prepare_value(self, value):
        """
        Performs value pre-processing before inserting it into the datastream.

        :param value: Raw value extracted from the datastream object
        :return: Processed value
        """

        return value

    def prepare_tags(self):
        """
        Returns a dictionary of tags that will be included in the final stream.
        """

        combined_tags = {
            'name': self.name,
        }
        combined_tags.update(self.custom_tags)
        return combined_tags

    def prepare_query_tags(self):
        """
        Returns a dict of tags that will be used to uniquely identify the final
        stream in addition to document-specific tags. This is usually a subset
        of tags returned by `prepare_tags`.
        """

        return {'name': self.name}

    def get_downsamplers(self):
        """
        Returns a list of downsamplers that will be used for the underlying stream.
        """

        return [
            'mean',
            'sum',
            'min',
            'max',
            'sum_squares',
            'std_dev',
            'count'
        ]

    def _process_tag_references(self, tags, descriptor):
        """
        Processes tags and resolves all tag references.

        :param tags: A dictionary of tags
        :param descriptor: Streams descriptor
        :return: Processed dictionary of tags
        """

        output = {}
        for key, value in tags.iteritems():
            if isinstance(value, dict):
                output[key] = self._process_tag_references(value, descriptor)
            elif isinstance(value, list):
                output[key] = []
                for item in value:
                    output[key].append(self._process_tag_references(item, descriptor))
            elif isinstance(value, TagReference):
                output[key] = value.resolve(descriptor)
            else:
                output[key] = value

        return output

    def process_tags(self, descriptor):
        """
        Returns a tuple (query_tags, tags) to be used by ensure_stream.
        """

        query_tags = descriptor.get_stream_query_tags()
        query_tags.update(self.prepare_query_tags())
        tags = descriptor.get_stream_tags()
        tags.update(self._process_tag_references(self.prepare_tags(), descriptor))
        return query_tags, tags

    def ensure_stream(self, descriptor, stream):
        """
        Creates stream and returns its identifier.

        :param descriptor: Destination stream descriptor
        :param stream: Stream API instance
        :return: Stream identifier
        """

        query_tags, tags = self.process_tags(descriptor)
        downsamplers = self.get_downsamplers()
        highest_granularity = descriptor.get_stream_highest_granularity()

        return stream.ensure_stream(query_tags, tags, downsamplers, highest_granularity)

    def to_stream(self, descriptor, stream):
        """
        Creates streams and inserts datapoints to the stream via the datastream API.

        :param descriptor: Destination stream descriptor
        :param stream: Stream API instance
        """

        attribute = self.name if self.attribute is None else self.attribute
        value = getattr(descriptor.get_model(), attribute)
        if value is None:
            return

        value = self.prepare_value(value)
        stream.append(self.ensure_stream(descriptor, stream), value)

    def set_tags(self, **tags):
        """
        Sets custom tags on this field.

        :param **tags: Keyword arguments describing the tags to set
        """

        def update(d, u):
            for k, v in u.iteritems():
                if isinstance(v, collections.Mapping):
                    r = update(d.get(k, {}), v)
                    d[k] = r
                else:
                    d[k] = u[k]
            return d

        update(self.custom_tags, tags)


class IntegerField(Field):
    """
    An integer-typed datastream field.
    """

    def __init__(self, **kwargs):
        """
        Class constructor.
        """

        super(IntegerField, self).__init__(**kwargs)

    def prepare_value(self, value):
        return int(value)

    def prepare_tags(self):
        tags = super(IntegerField, self).prepare_tags()
        tags.update({'type': 'integer'})
        return tags


class FloatField(Field):
    """
    A float-typed datastream field.
    """

    def __init__(self, **kwargs):
        """
        Class constructor.
        """

        super(FloatField, self).__init__(**kwargs)

    def prepare_value(self, value):
        return float(value)

    def prepare_tags(self):
        tags = super(FloatField, self).prepare_tags()
        tags.update({'type': 'float'})
        return tags


class DerivedField(Field):
    """
    A derived datastream field.
    """

    def __init__(self, streams, op, arguments=None, **kwargs):
        """
        Class constructor.

        :param streams: A list of input stream descriptors
        :param op: Operator name
        :param arguments: Optional operator arguments
        """

        self.streams = streams
        self.op = op
        self.op_arguments = arguments or {}

        super(DerivedField, self).__init__(**kwargs)

    def ensure_stream(self, descriptor, stream):
        """
        Creates stream and returns its identifier.

        :param descriptor: Destination stream descriptor
        :param stream: Stream API instance
        :return: Stream identifier
        """

        # Acquire references to input streams
        root = descriptor.get_model().root
        streams = []
        for field_ref in self.streams:
            path, field = field_ref['field'].split('#')
            mdl = descriptor.get_model()
            if path:
                mdl = root.monitoring.by_path(path)

            mdl_descriptor = pool.get_descriptor(mdl)
            field = mdl_descriptor.get_field(field)
            if field is None:
                raise exceptions.ImproperlyConfigured("Datastream field '%s' not found!" % field_ref['field'])

            streams.append(
                {'name': field_ref['name'], 'stream': field.ensure_stream(mdl_descriptor, stream)}
            )

        query_tags, tags = self.process_tags(descriptor)
        downsamplers = self.get_downsamplers()
        highest_granularity = descriptor.get_stream_highest_granularity()

        return stream.ensure_stream(
            query_tags,
            tags,
            downsamplers,
            highest_granularity,
            derive_from=streams,
            derive_op=self.op,
            derive_args=self.op_arguments,
        )

    def to_stream(self, descriptor, stream):
        """
        Creates streams and inserts datapoints to the stream via the datastream API.

        :param descriptor: Destination stream descriptor
        :param stream: Stream API instance
        """

        self.ensure_stream(descriptor, stream)


class ResetField(DerivedField):
    """
    A field that generates a reset stream.
    """

    def __init__(self, field, **kwargs):
        """
        Class constructor.
        """

        super(ResetField, self).__init__(
            [{'name': 'reset', 'field': field}],
            'counter_reset',
            **kwargs
        )


class RateField(DerivedField):
    """
    A rate datastream field.
    """

    def __init__(self, reset_field, data_field, max_value=None, **kwargs):
        """
        Class constructor.
        """

        super(RateField, self).__init__(
            [
                {'name': 'reset', 'field': reset_field},
                {'name': None, 'field': data_field},
            ],
            'counter_derivative',
            arguments={
                'max_value': max_value,
            },
            **kwargs
        )


class DynamicSumField(Field):
    """
    A field that computes a sum of other source fields, the list of which
    can be dynamically modified. The underlying derived stream is automatically
    recreated whenever the set of source streams changes.
    """

    def __init__(self, **kwargs):
        """
        Class constructor.
        """

        self._fields = []

        super(DynamicSumField, self).__init__(**kwargs)

    def clear_source_fields(self):
        """
        Clears all the source fields.
        """

        self._fields = []

    def add_source_field(self, field, descriptor):
        """
        Adds a source field.
        """

        self._fields.append((field, descriptor))

    def ensure_stream(self, descriptor, stream):
        """
        Creates stream and returns its identifier.

        :param descriptor: Destination stream descriptor
        :param stream: Stream API instance
        :return: Stream identifier
        """

        # Generate a list of input streams
        streams = []
        for src_field, src_descriptor in self._fields:
            streams.append(
                {'stream': src_field.ensure_stream(src_descriptor, stream)}
            )

        if not streams:
            return

        query_tags, tags = self.process_tags(descriptor)
        downsamplers = self.get_downsamplers()
        highest_granularity = descriptor.get_stream_highest_granularity()

        try:
            return stream.ensure_stream(
                query_tags,
                tags,
                downsamplers,
                highest_granularity,
                derive_from=streams,
                derive_op='sum',
                derive_args={},
            )
        except ds_exceptions.InconsistentStreamConfiguration:
            # Drop the existing stream and re-create it
            stream.remove_streams(query_tags)
            return stream.ensure_stream(
                query_tags,
                tags,
                downsamplers,
                highest_granularity,
                derive_from=streams,
                derive_op='sum',
                derive_args={},
            )

    def to_stream(self, descriptor, stream):
        """
        Creates streams and inserts datapoints to the stream via the datastream API.

        :param descriptor: Destination stream descriptor
        :param stream: Stream API instance
        """

        self.ensure_stream(descriptor, stream)
