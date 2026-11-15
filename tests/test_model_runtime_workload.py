import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

from akira_model_runtime import ManagedLlamaProcess, _model_gpu, hardware_profile


class ModelWorkload(unittest.TestCase):
    def test_available_nvidia_memory_beats_vulkan_budget(self):
        def probe(command, **kwargs):
            output = (
                'NVIDIA GeForce RTX 5060 Ti, 1858\n' if command[0] == 'nvidia-smi'
                else '  Vulkan0: NVIDIA GeForce RTX 5060 Ti (7891 MiB, 7123 MiB free)\n'
            )
            return CompletedProcess(command, 0, output, '')

        gpu = _model_gpu(Path('bin/llama-server.exe'), run=probe)
        self.assertEqual(gpu['available_mib'], 1858)
        self.assertIsNone(gpu['fit_target_mib'])
        runtime = ManagedLlamaProcess({}, profile=hardware_profile(32, 8, 20))
        runtime._gpu_probe = gpu
        runtime._gpu_allowed_at_launch = True
        with patch.object(runtime, '_paths', return_value=(Path('bin/llama-server.exe'), Path('model.gguf'))):
            runtime._launch_command = runtime.command('http://127.0.0.1:18987/v1/chat/completions')
        self.assertEqual(runtime.effective_parameters()['gpu_layers'], 0)
        self.assertEqual(runtime.effective_parameters()['gpu_device'], 'NVIDIA GeForce RTX 5060 Ti')
        self.assertIn('VRAM libre insuficiente', runtime.effective_parameters()['gpu_status'])

    def test_amd_device_is_used_with_vram_headroom(self):
        def probe(command, **kwargs):
            return CompletedProcess(
                command, 0, '', '  Vulkan1: AMD Radeon RX 6600 (8192 MiB, 4900 MiB free)\n',
            )

        gpu = _model_gpu(Path('bin/llama-server.exe'), run=probe)
        self.assertEqual(gpu['device'], 'Vulkan1')
        with patch('resource_optimizer.desktop_hardware', return_value={
            'ram_gb': 32, 'physical_cores': 12, 'dedicated_gpu': True,
        }):
            runtime = ManagedLlamaProcess({}, profile=hardware_profile(32, cpu_cores=20))
        runtime._gpu_probe = gpu
        with patch.object(runtime, '_paths', return_value=(Path('bin/llama-server.exe'), Path('model.gguf'))):
            endpoint = 'http://127.0.0.1:18987/v1/chat/completions'
            command = runtime.command(endpoint, {'performance_profile': 'Rendimiento'})
            cpu_command = runtime.command(endpoint, {'model_use_gpu': False})
        options = dict(zip(command[1::2], command[2::2]))
        self.assertEqual(options['--n-gpu-layers'], 'auto')
        self.assertEqual(options['--threads'], '4')
        self.assertEqual(command[command.index('--device') + 1], 'Vulkan1')
        self.assertEqual(command[command.index('--fit-target') + 1], '1024')
        self.assertNotIn('--device', cpu_command)
        self.assertEqual(cpu_command[cpu_command.index('--n-gpu-layers') + 1], '0')

    def test_thread_budget_leaves_room_for_other_components(self):
        with patch('resource_optimizer.desktop_hardware', return_value={'physical_cores': 12}):
            self.assertEqual(hardware_profile(32, cpu_cores=4)['cpu_threads'], 2)
            self.assertEqual(hardware_profile(32, cpu_cores=20)['cpu_threads'], 8)
            self.assertEqual(hardware_profile(8, cpu_cores=20)['cpu_threads'], 2)
        with patch('resource_optimizer.desktop_hardware', return_value={'physical_cores': 2}):
            self.assertEqual(hardware_profile(8, cpu_cores=4)['cpu_threads'], 1)

    def test_offload_reports_only_current_startup(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = ManagedLlamaProcess({}, profile=hardware_profile(8, 0, 4), log_root=tmp)
            runtime._launch_command = ['llama-server', '--n-gpu-layers', 'auto']
            runtime.log_path.parent.mkdir()
            previous = b'load_tensors: offloaded 33/33 layers to GPU\n'
            runtime._log_start_offset = len(previous)
            runtime.log_path.write_bytes(previous)
            runtime._read_offload_result()
            self.assertIsNone(runtime.effective_parameters()['gpu_layers'])
            with runtime.log_path.open('ab') as stream:
                stream.write(b'load_tensors: offloaded 12/33 layers to GPU\n')
            runtime._read_offload_result()
            self.assertEqual(runtime.effective_parameters()['gpu_layers'], 12)
