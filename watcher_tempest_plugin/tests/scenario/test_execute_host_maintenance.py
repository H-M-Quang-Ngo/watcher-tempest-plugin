# -*- encoding: utf-8 -*-
#
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from oslo_log import log
from tempest.common import waiters
from tempest import config
from tempest.lib import decorators
from watcher_tempest_plugin.tests.scenario import base

CONF = config.CONF
LOG = log.getLogger(__name__)


class TestExecuteHostMaintenanceStrategy(base.BaseInfraOptimScenarioTest):
    """Tests for host_maintenance"""

    # Minimal version required for _create_one_instance_per_host
    compute_min_microversion = base.NOVA_API_VERSION_CREATE_WITH_HOST

    GOAL = "cluster_maintaining"

    @classmethod
    def skip_checks(cls):
        super(TestExecuteHostMaintenanceStrategy, cls).skip_checks()

    @classmethod
    def resource_setup(cls):
        super(TestExecuteHostMaintenanceStrategy, cls).resource_setup()
        if CONF.compute.min_compute_nodes < 2:
            raise cls.skipException(
                "Less than 2 compute nodes, skipping multinode tests.")
        if not CONF.compute_feature_enabled.live_migration:
            raise cls.skipException("Live migration is not enabled")

        enabled_compute_nodes = cls.get_enabled_compute_nodes()
        cls.wait_for_compute_node_setup()

        if len(enabled_compute_nodes) < 2:
            raise cls.skipException(
                "Less than 2 compute nodes are enabled, "
                "skipping multinode tests.")

    @decorators.idempotent_id('17afd352-1929-46dd-a10a-63c90bb9255d')
    @decorators.attr(type=['strategy', 'host_maintenance'])
    def test_execute_host_maintenance_strategy(self):
        # This test does not require metrics injection

        self.addCleanup(self.rollback_compute_nodes_status)
        self.addCleanup(self.wait_delete_instances_from_model)
        instances = self._create_one_instance_per_host()
        # wait for compute model updates
        self.wait_for_instances_in_model(instances)

        src_node = self.get_host_for_server(instances[0]['id'])

        goal_name = "cluster_maintaining"
        strategy_name = "host_maintenance"
        audit_kwargs = {
            "parameters": {
                "maintenance_node": src_node
            }
        }
        self.execute_strategy(goal_name, strategy_name,
                              expected_actions=['change_nova_service_state',
                                                'migrate'],
                              **audit_kwargs)

    @decorators.idempotent_id('cc5a0f1b-e8d2-4813-b012-874982d15d06')
    @decorators.attr(type=['strategy', 'host_maintenance'])
    def test_execute_host_maintenance_strategy_backup_node(self):
        # This test does not require metrics injection

        self.addCleanup(self.rollback_compute_nodes_status)
        self.addCleanup(self.wait_delete_instances_from_model)
        instances = self._create_one_instance_per_host()
        # wait for compute model updates
        self.wait_for_instances_in_model(instances)

        src_node = self.get_host_for_server(instances[0]['id'])
        dst_node = self.get_host_other_than(instances[0]['id'])

        goal_name = "cluster_maintaining"
        strategy_name = "host_maintenance"
        audit_kwargs = {
            "parameters": {
                "maintenance_node": src_node,
                "backup_node": dst_node
            }
        }

        self.execute_strategy(goal_name, strategy_name,
                              expected_actions=['change_nova_service_state',
                                                'migrate'],
                              **audit_kwargs)

        # Make sure servers are migrated to backup node
        for server in instances:
            self.assertEqual(self.get_host_for_server(server['id']), dst_node)

    @decorators.idempotent_id('a1b2c3d4-e5f6-7890-ab12-cd34ef567890')
    @decorators.attr(type=['strategy', 'host_maintenance'])
    def test_execute_host_maintenance_disable_live_migration(self):
        # This test verifies that when live migration is disabled,
        # active instances are cold migrated to other nodes

        self.addCleanup(self.rollback_compute_nodes_status)
        self.addCleanup(self.wait_delete_instances_from_model)
        instances = self._create_one_instance_per_host()
        # wait for compute model updates
        self.wait_for_instances_in_model(instances)

        src_node = self.get_host_for_server(instances[0]['id'])
        # Store initial host locations
        initial_hosts = {
            instance['id']: self.get_host_for_server(instance['id'])
            for instance in instances
        }

        goal_name = "cluster_maintaining"
        strategy_name = "host_maintenance"
        audit_kwargs = {
            "parameters": {
                "maintenance_node": src_node,
                "disable_live_migration": True
            }
        }
        self.execute_strategy(goal_name, strategy_name,
                              expected_actions=['change_nova_service_state',
                                                'migrate'],
                              **audit_kwargs)

        # Verify instances are (cold) migrated to different nodes
        for instance in instances:
            if initial_hosts[instance['id']] == src_node:
                new_host = self.get_host_for_server(instance['id'])
                self.assertNotEqual(
                    initial_hosts[instance['id']], new_host)
                # Verify instance is active after cold migration
                server = self.mgr.servers_client.show_server(
                    instance['id'])['server']
                self.assertEqual('ACTIVE', server['status'])

    @decorators.idempotent_id('053025b9-acdf-4bf5-b3c3-a132396a2de4')
    @decorators.attr(type=['strategy', 'host_maintenance'])
    def test_execute_host_maintenance_disable_cold_migration(self):
        # This test verifies that when cold migration is disabled,
        # active instances are live migrated (cold migration disabled
        # doesn't affect active instances)

        self.addCleanup(self.rollback_compute_nodes_status)
        self.addCleanup(self.wait_delete_instances_from_model)
        instances = self._create_one_instance_per_host()
        # wait for compute model updates
        self.wait_for_instances_in_model(instances)

        src_node = self.get_host_for_server(instances[0]['id'])

        goal_name = "cluster_maintaining"
        strategy_name = "host_maintenance"
        audit_kwargs = {
            "parameters": {
                "maintenance_node": src_node,
                "disable_cold_migration": True
            }
        }
        self.execute_strategy(goal_name, strategy_name,
                              expected_actions=['change_nova_service_state',
                                                'migrate'],
                              **audit_kwargs)

    @decorators.idempotent_id('31b8523e-2f5b-4002-a3cf-678fbc215f0b')
    @decorators.attr(type=['strategy', 'host_maintenance'])
    def test_exec_host_maintenance_disable_cold_inactive_instances(self):
        # This test verifies that when cold migration is disabled,
        # inactive instances are unaffected.

        self.addCleanup(self.rollback_compute_nodes_status)
        self.addCleanup(self.wait_delete_instances_from_model)
        instances = self._create_one_instance_per_host()
        # wait for compute model updates
        self.wait_for_instances_in_model(instances)

        src_node = self.get_host_for_server(instances[0]['id'])

        # Create inactive instances by pausing some instances
        inactive_instances = []
        for instance in instances:
            if self.get_host_for_server(instance['id']) == src_node:
                # Stop the instance to make it inactive
                self.mgr.servers_client.pause_server(instance['id'])
                # Wait for the instance to be paused
                waiters.wait_for_server_status(
                    self.mgr.servers_client, instance['id'], 'PAUSED'
                )
                inactive_instances.append(instance)

        # Wait for compute model updates
        self.wait_for_instances_in_model(instances)

        goal_name = "cluster_maintaining"
        strategy_name = "host_maintenance"
        audit_kwargs = {
            "parameters": {
                "maintenance_node": src_node,
                "disable_cold_migration": True
            }
        }

        # No migrations should occur, only change_nova_service_state
        self.execute_strategy(goal_name, strategy_name,
                              expected_actions=['change_nova_service_state'],
                              **audit_kwargs)

        # Verify inactive instances remain on the same host and stay paused
        for instance in inactive_instances:
            current_host = self.get_host_for_server(instance['id'])
            self.assertEqual(current_host, src_node)
            server = self.mgr.servers_client.show_server(
                instance['id'])['server']
            self.assertEqual('PAUSED', server['status'])

    @decorators.idempotent_id('863b16b5-3c74-413c-98a8-d9ce5deb539c')
    @decorators.attr(type=['strategy', 'host_maintenance'])
    def test_execute_host_maintenance_disable_both_migrations(self):
        # This test verifies that when both migrations are disabled,
        # active instances are stopped instead of migrated

        self.addCleanup(self.rollback_compute_nodes_status)
        self.addCleanup(self.wait_delete_instances_from_model)
        instances = self._create_one_instance_per_host()
        # wait for compute model updates
        self.wait_for_instances_in_model(instances)

        src_node = self.get_host_for_server(instances[0]['id'])

        goal_name = "cluster_maintaining"
        strategy_name = "host_maintenance"
        audit_kwargs = {
            "parameters": {
                "maintenance_node": src_node,
                "disable_live_migration": True,
                "disable_cold_migration": True
            }
        }
        self.execute_strategy(goal_name, strategy_name,
                              expected_actions=['change_nova_service_state',
                                                'stop'],
                              **audit_kwargs)

        # Wait for compute model updates
        self.wait_for_instances_in_model(instances)

        # Verify instances on maintenance node are stopped
        for instance in instances:
            current_host = self.get_host_for_server(instance['id'])
            if current_host == src_node:
                server = self.mgr.servers_client.show_server(
                    instance['id'])['server']
                self.assertEqual('SHUTOFF', server['status'])
                # Verify instance remains on the same host (not migrated)
                self.assertEqual(current_host, src_node)

    @decorators.idempotent_id('f5e6d7c8-1234-5678-9012-ab34cd56ef78')
    @decorators.attr(type=['strategy', 'host_maintenance'])
    def test_exec_host_maintenance_disable_migration_inactive_instances(self):
        # This test creates inactive instances to verify that when both
        # migrations are disabled, only change_nova_service_state occurs

        self.addCleanup(self.rollback_compute_nodes_status)
        self.addCleanup(self.wait_delete_instances_from_model)
        instances = self._create_one_instance_per_host()
        # wait for compute model updates
        self.wait_for_instances_in_model(instances)

        src_node = self.get_host_for_server(instances[0]['id'])

        # Create inactive instances by stopping some instances
        inactive_instances = []
        for instance in instances:
            if self.get_host_for_server(instance['id']) == src_node:
                # Stop the instance to make it inactive
                self.mgr.servers_client.stop_server(instance['id'])
                # Wait for the instance to be stopped
                waiters.wait_for_server_status(
                    self.mgr.servers_client, instance['id'], 'SHUTOFF'
                )
                inactive_instances.append(instance)

        # Wait for compute model updates
        self.wait_for_instances_in_model(instances)

        goal_name = "cluster_maintaining"
        strategy_name = "host_maintenance"
        audit_kwargs = {
            "parameters": {
                "maintenance_node": src_node,
                "disable_live_migration": True,
                "disable_cold_migration": True
            }
        }

        # No migrations should occur, only change_nova_service_state
        self.execute_strategy(goal_name, strategy_name,
                              expected_actions=['change_nova_service_state'],
                              **audit_kwargs)

        # Verify inactive instances remain on the same host and stay stopped
        for instance in inactive_instances:
            current_host = self.get_host_for_server(instance['id'])
            self.assertEqual(current_host, src_node)
            server = self.mgr.servers_client.show_server(
                instance['id'])['server']
            self.assertEqual('SHUTOFF', server['status'])
