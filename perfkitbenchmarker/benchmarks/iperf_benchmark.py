# Copyright 2014 Google Inc. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Runs plain Iperf.

Docs:
http://iperf.fr/

Runs Iperf to collect network throughput.
"""

import re

import gflags as flags
import logging

from perfkitbenchmarker import perfkitbenchmarker_lib

FLAGS = flags.FLAGS

BENCHMARKS_INFO = {'name': 'iperf',
                   'description': 'Run iperf',
                   'scratch_disk': False,
                   'num_machines': 2}

IPERF_PORT = 20000


def GetInfo():
  return BENCHMARKS_INFO


def Prepare(benchmark_spec):
  """Install iperf and start the server on all machines.

  Args:
    benchmark_spec: The benchmark specification. Contains all data that is
        required to run the benchmark.
  """

  fw = benchmark_spec.firewall
  vms = benchmark_spec.vms
  for vm in vms:
    vm.InstallPackage('iperf')
    fw.AllowPort(vm, IPERF_PORT)
    vm.RemoteCommand('nohup iperf --server --port %s &> /dev/null &' %
                     IPERF_PORT)


def _RunIperf(sending_vm, receiving_vm, receiving_ip_address, ip_type):
  """Run iperf using sending 'vm' to connect to 'ip_address'.

  Args:
    sending_vm: The VM sending traffic.
    receiving_vm: The VM receiving traffic.
    ip_address: The IP address of the iperf server (ie the receiver).
    ip_type: The IP type of 'ip_address' (e.g. 'internal', 'external')
  Returns:
    A single sample (see 'Run' docstring for sample type description).
  Raises:
    ValueError: When iperf results are not found in stdout.
  """
  iperf_cmd = ('iperf --client %s --port %s --format m --time 60' %
               (receiving_ip_address, IPERF_PORT))
  iperf_pattern = re.compile(r'(\d+\.\d+|\d+) Mbits/sec')
  stdout, _ = sending_vm.RemoteCommand(iperf_cmd, should_log=True)
  match = iperf_pattern.search(stdout)
  if not match:
    raise ValueError('Could not find iperf result in stdout:\n\n%s' % stdout)
  value = match.group(1)

  metadata = {
      # TODO(voellm): The server and client terminology is being
      # deprecated.  It does not make clear the direction of the flow.
      'server_machine_type': receiving_vm.machine_type,
      'server_zone': receiving_vm.zone,
      'client_machine_type': sending_vm.machine_type,
      'client_zone': sending_vm.zone,

      # The meta data defining the environment
      'receiving_machine_type': receiving_vm.machine_type,
      'receiving_zone': receiving_vm.zone,
      'sending_machine_type': sending_vm.machine_type,
      'sending_zone': sending_vm.zone,
      'ip_type': ip_type
  }
  return ('Throughput', float(value), 'Mbits/sec', metadata)


def Run(benchmark_spec):
  """Run iperf on the target vm.

  Args:
    benchmark_spec: The benchmark specification. Contains all data that is
        required to run the benchmark.

  Returns:
    A list of samples in the form of 3 or 4 tuples. The tuples contain
        the sample metric (string), value (float), and unit (string).
        If a 4th element is included, it is a dictionary of sample
        metadata.
  """
  vms = benchmark_spec.vms
  results = []

  logging.info('Iperf Results:')

  # Send traffic in both directions
  for originator in [0, 1]:
    sending_vm = vms[originator]
    receiving_vm = vms[originator ^ 1]
    # Send using external IP addresses
    if perfkitbenchmarker_lib.ShouldRunOnExternalIpAddress():
      results.append(_RunIperf(sending_vm,
                               receiving_vm,
                               receiving_vm.ip_address,
                               'external'))

    # Send using internal IP addresses
    if perfkitbenchmarker_lib.ShouldRunOnInternalIpAddress(sending_vm,
                                                           receiving_vm):
      results.append(_RunIperf(sending_vm,
                               receiving_vm,
                               receiving_vm.internal_ip,
                               'internal'))

  return results


def Cleanup(benchmark_spec):
  """Cleanup iperf on the target vm (by uninstalling).

  Args:
    benchmark_spec: The benchmark specification. Contains all data that is
        required to run the benchmark.
  """
  vms = benchmark_spec.vms
  vms[1].RemoteCommand('pkill -9 iperf')

  for vm in vms:
    vm.UninstallPackage('iperf')
