from __future__ import annotations

from ai_mcu_debug.models import BuildConfig

from .command import CommandBuildAdapter


class CMakeBuildAdapter(CommandBuildAdapter):
    def __init__(self, config: BuildConfig) -> None:
        if config.build_command is None:
            config = BuildConfig(
                backend=config.backend,
                build_dir=config.build_dir,
                source_dir=config.source_dir,
                configure_command=config.configure_command,
                build_command=["cmake", "--build", str(config.build_dir)],
                flash_command=config.flash_command,
                smoke_test_command=config.smoke_test_command,
                runtime_log_command=config.runtime_log_command,
                repair_command=config.repair_command,
                command_timeout_s=config.command_timeout_s,
                runtime_log_timeout_s=config.runtime_log_timeout_s,
                repair_timeout_s=config.repair_timeout_s,
                max_repair_iterations=config.max_repair_iterations,
                extra=config.extra,
            )
        super().__init__(config)
