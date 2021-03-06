from nodewatcher.core.monitor import processors as monitor_processors
from nodewatcher.modules.monitor.sources.http import processors as http_processors


class GenericSensors(monitor_processors.NodeProcessor):
    """
    Stores generic sensor monitor data into the database. Will only run if HTTP
    monitor module has previously fetched data.
    """

    @monitor_processors.depends_on_context("http", http_processors.HTTPTelemetryContext)
    def process(self, context, node):
        """
        Called for every processed node.

        :param context: Current context
        :param node: Node that is being processed
        :return: A (possibly) modified context
        """

        version = context.http.get_module_version('sensors.generic')

        if version >= 1:
            for sensor_id, data in context.http.sensors.generic.items():
                node.monitoring.sensors.generic(queryset=True).update_or_create(
                    sensor_id=sensor_id,
                    defaults={
                        'name': str(data.name or ''),
                        'unit': str(data.unit or ''),
                        'value': float(data.value),
                    }
                )

        return context
