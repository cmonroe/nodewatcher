from ....utils import loader

from ...registry import registration

from . import devices as cgm_devices, resources as cgm_resources, exceptions
from .. import models as generator_models

# Registered platform modules
PLATFORM_REGISTRY = {}


class ValidationError(Exception):
    pass


class PlatformAccountManager(object):
    """
    A simple platform-independent account manager.
    """

    def __init__(self):
        """
        Class constructor.
        """

        self._users = {}

    def add_user(self, username, password, uid, gid, home, shell):
        """
        Creates a new user account on the device.

        :param username: Username
        :param password: Clear-text password
        :param uid: UID
        :param gid: GID
        :param home: Home directory location
        :param shell: Shell
        """

        self._users[uid] = {
            'uid': int(uid),
            'gid': int(gid),
            'home': str(home).encode('ascii'),
            'shell': str(shell).encode('ascii'),
            'username': str(username).encode('ascii'),
            'password': str(password),
        }

    def get_config(self):
        """
        Returns a configuration dictionary suitable for use in JSON
        documents.
        """

        return {
            'users': self._users,
        }


class PlatformRoutingTableManager(object):
    """
    Configure routing table mappings from name to identifier.
    """

    def __init__(self):
        """
        Class constructor.
        """

        self._tables = {}

    def set_table(self, name, identifier):
        """
        Configures a routing table name to identifier mapping.

        :param name: Routing table name
        :param identifier: Routing table platform-specific identifier
        """

        self._tables[identifier] = name

    def get_config(self):
        """
        Returns a configuration dictionary suitable for use in JSON
        documents.
        """

        return self._tables


class PlatformCryptoManager(object):
    """
    Configure platform cryptographic objects like certificates, public and
    private keys.
    """

    # Object types.
    CERTIFICATE = 1
    PUBLIC_KEY = 2
    PRIVATE_KEY = 3
    SYMMETRIC_KEY = 4
    SSH_AUTHORIZED_KEY = 5

    class CryptoObject(object):
        def __init__(self, object_type, content, name):
            """
            Class constructor.
            """

            self.object_type = object_type
            self.content = content
            self.name = name

        def path(self):
            """
            This method should be overriden by the platform-specific implementation
            to return the path to the crypto object on the filesystem.
            """

            raise NotImplementedError

        def get_config(self):
            """
            Returns a configuration dictionary suitable for use in JSON
            documents.
            """

            return {
                'type': self.object_type,
                'name': self.name,
                'content': self.content,
            }

    object_class = CryptoObject

    def __init__(self):
        """
        Class constructor.
        """

        self._objects = {}

    def add_object(self, object_type, content, name):
        """
        Adds a new crypto object.

        :param object_type: Type of the crypto object
        :param content: Object content
        :param name: Unique object name
        :return: Crypto object instance
        """

        # TODO: Perform object validation and raise ValidationErrors.

        name = str(name)

        crypto_object = self.object_class(object_type, content.strip(), name)
        objects = self._objects.setdefault(object_type, {})
        objects[name] = crypto_object

        return crypto_object

    def get_object(self, object_type, name):
        """
        Returns an existing crypto object.

        :param object_type: Type of the crypto object
        :param name: Unique object name
        :return: Crypto object instance
        """

        return self._objects[object_type][name]

    def get_config(self):
        """
        Returns a list of crypto objects suitable for use in JSON documents.
        """

        config = []
        for object_type, objects in self._objects.items():
            for crypto_object in objects.values():
                config.append(crypto_object.get_config())

        return config


class PlatformConfiguration(object):
    """
    A flexible in-memory platform configuration store that is used
    by modules to make modifications and perform configuration. The
    default implementation only contains some platform-independent
    methods.
    """

    resources_class = cgm_resources.ResourceAllocator
    packages_class = set
    accounts_class = PlatformAccountManager
    routing_table_manager_class = PlatformRoutingTableManager
    crypto_manager_class = PlatformCryptoManager

    def __init__(self):
        """
        Class constructor.
        """

        self.resources = self.resources_class()
        self.packages = self.packages_class()
        self.accounts = self.accounts_class()
        self.banner = str()
        self.routing_tables = self.routing_table_manager_class()
        self.crypto = self.crypto_manager_class()

    def get_build_config(self):
        """
        Returns a build configuration which must be JSON-serializable. This
        configuration will be passed to the backend builder function and must
        contain anything that the builder will need to configure the generated
        firmware.
        """

        return {
            '_packages': list(self.packages),
            '_accounts': self.accounts.get_config(),
            '_banner': str(self.banner),
            '_routing_tables': self.routing_tables.get_config(),
            '_crypto': self.crypto.get_config(),
        }


class PlatformBase(object):
    """
    An abstract base class for all platform implementations.
    """

    config_class = PlatformConfiguration

    def __init__(self):
        """
        Class constructor.
        """

        self.name = None
        self._modules = []
        self._packages = []
        self._devices = {}

    def generate(self, node):
        """
        Generates a concrete configuration for this platform.
        """

        cfg = self.config_class()

        # Execute the module chain in order
        for _, module, device in sorted(self._modules):
            if device is None or device == node.config.core.general().router:
                module(node, cfg)

        # Process user-configured packages
        for name, cfgclass, package in self._packages:
            pkgcfg = node.config.core.packages(onlyclass=cfgclass)
            if [x for x in pkgcfg if x.enabled]:
                package(node, pkgcfg, cfg)
                cfg.packages.add(name)

        return cfg

    def build(self, result):
        """
        Builds the firmware using a previously generated and properly
        formatted configuration.

        :param result: Destination build result
        :return: A list of generated firmware files
        """

        raise NotImplementedError

    def defer_build(self, user, node, cfg):
        """
        Deferrs formatting and building to a background Celery job. The job
        is responsible for calling proper format and build methods on this
        platform.

        :param user: User that is generating the firmware
        :param node: Node instance to generate the firmware for
        :param cfg: Generated configuration (platform-dependent)
        :return: New build result instance
        """

        build_channel, builder = self.validate_build(node, cfg)
        result = generator_models.BuildResult(
            user=user,
            node=node,
            config=cfg.get_build_config(),
            build_channel=build_channel,
            builder=builder,
            status=generator_models.BuildResult.PENDING,
        )
        result.save()

        from . import tasks
        tasks.background_build.delay(result.uuid)

        return result

    def validate_build(self, node, cfg):
        """
        Validates the build configuration.

        :param node: Node instance to generate the firmware for
        :param cfg: Generated configuration (platform-dependent)
        """

        build_channel, builder = self.get_builder(node)

        return build_channel, builder

    def get_builder(self, node):
        """
        Returns a builder suitable for building a firmware image for the
        specified node.

        :param node: Node instance to generate the firmware for
        :return: A tuple (build_channel, builder)
        """

        build_channel = node.config.core.general().build_channel
        version = node.config.core.general().version
        device = node.config.core.general().get_device()

        if build_channel is None:
            # Default build channel specified, use it if one is selected
            try:
                build_channel = generator_models.BuildChannel.objects.get(default=True)
            except generator_models.BuildChannel.DoesNotExist:
                raise exceptions.NoBuildChannelsConfigured

        if version is None:
            # Build channel specified, use the latest version
            try:
                version = generator_models.BuildVersion.objects.filter(
                    builders__channels=build_channel
                ).latest('created')
            except generator_models.BuildVersion.DoesNotExist:
                raise exceptions.NoBuildersConfigured

        # Select a proper builder
        try:
            builder = generator_models.Builder.objects.get(
                platform=self.name,
                architecture=device.architecture,
                channels=build_channel,
                version=version,
            )
        except generator_models.Builder.DoesNotExist:
            raise exceptions.NoSuitableBuildersFound

        return build_channel, builder

    def register_module(self, weight, module, device=None):
        """
        Registers a new platform module.

        :param weight: Call order weight
        :param module: Module implementation function
        :param device: Optional device identifier
        """

        if [x for x in self._modules if x[1] == module and x[2] == device]:
            return

        self._modules.append((weight, module, device))

    def register_package(self, name, config, package):
        """
        Registers a new platform package.

        :param name: Platform-dependent package name
        :param config: Configuration class
        :param package: Package implementation function
        """

        if [x for x in self._packages if x[2] == package]:
            return

        self._packages.append((name, config, package))

    def register_device(self, device):
        """
        Registers a new device with this platform.

        :param device: A subclass of DeviceBase
        """

        if not issubclass(device, cgm_devices.DeviceBase):
            raise TypeError("Router descriptor must be a subclass of DeviceBase!")

        self._devices[device.identifier] = device
        device.register(self)

    def get_device(self, device):
        """
        Returns a device descriptor.

        :param device: Unique device identifier
        """

        return self._devices[device]


def register_platform(enum, text, platform):
    """
    Registers a new platform with the Configuration Generation Modules
    system.
    """

    if not isinstance(platform, PlatformBase):
        raise TypeError("Platform formatter/builder implementation must be a PlatformBase instance!")

    if enum in PLATFORM_REGISTRY:
        raise ValueError("Platform '{0}' is already registered!".format(enum))

    PLATFORM_REGISTRY[enum] = platform
    platform.name = enum

    # Register the choice in configuration registry
    registration.point("node.config").register_choice("core.general#platform", registration.Choice(enum, text))


def get_platform(platform):
    """
    Returns the given platform implementation.
    """

    # Ensure that all CGMs are registred
    loader.load_modules('cgm')

    try:
        return PLATFORM_REGISTRY[platform]
    except KeyError:
        raise KeyError("Platform '{0}' does not exist!".format(platform))


def register_platform_module(platform, weight=999, device=None):
    """
    Registers a new platform module.
    """

    def wrapper(f):
        get_platform(platform).register_module(weight, f, device=device)
        return f

    return wrapper


def register_platform_package(platform, name, cfgclass):
    """
    Registers a new platform package.
    """

    def wrapper(f):
        get_platform(platform).register_package(name, cfgclass, f)
        return f

    return wrapper


def register_device(platform, device):
    """
    Registers a new device.
    """

    get_platform(platform).register_device(device)


def iterate_devices():
    """
    Iterates over all registered devices.
    """

    for platform in PLATFORM_REGISTRY.values():
        for device in platform._devices.values():
            yield device


def generate_firmware(node, user=None, only_validate=False):
    """
    Generates configuration and/or firmware for the specified node.

    :param node: Node instance
    :param user: User that will own the firmware image
    :param only_validate: True if only validation should be performed
    """

    # Determine the destination platform
    try:
        platform = get_platform(node.config.core.general().platform)
    except (AttributeError, KeyError):
        return None

    cfg = platform.generate(node)
    if not only_validate:
        if user is None:
            raise ValueError('To build firmware images, the \'user\' argument must be specified!')

        return platform.defer_build(user, node, cfg)
    else:
        # Ensure that the proper builders are available for building this firmware
        platform.validate_build(node, cfg)

    return cfg
