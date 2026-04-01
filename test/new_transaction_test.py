import datetime
import json
import os
import tempfile
import unittest
from decimal import Decimal

from henry.base.fileservice import FileService
from henry.base.serialization import json_dumps
from henry.product.dao import InventoryApi, InventoryMovement, InvMovementType


class InventoryApiTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.api = InventoryApi(FileService(self.tempdir.name))
        self.itemgroup_id = 1

    def make_movement(self, **overrides):
        movement = InventoryMovement(
            from_inv_id=None,
            to_inv_id=None,
            quantity=Decimal('0'),
            itemgroup_id=self.itemgroup_id,
            prod_id='AAAA',
            timestamp=datetime.datetime(2016, 1, 1, 8, 0, 0),
            type=InvMovementType.TRANSFER,
        )
        for key, value in overrides.items():
            setattr(movement, key, value)
        return movement

    def test_get_current_quantity_returns_empty_for_unknown_itemgroup(self):
        self.assertDictEqual({}, dict(self.api.get_current_quantity(999)))

    def test_save_and_list_transactions_persist_json_lines_by_month(self):
        jan_movement = self.make_movement(
            from_inv_id=1,
            to_inv_id=2,
            quantity=Decimal('1.5'),
            timestamp=datetime.datetime(2016, 1, 1, 10, 30, 0),
            type=InvMovementType.SALE)
        feb_movement = self.make_movement(
            from_inv_id=None,
            to_inv_id=3,
            quantity=Decimal('4'),
            timestamp=datetime.datetime(2016, 2, 2, 11, 0, 0),
            type=InvMovementType.INGRESS)

        self.api.save(jan_movement)
        self.api.save(feb_movement)

        jan_path = os.path.join(
            self.tempdir.name,
            str(self.itemgroup_id),
            '2016-01')
        feb_path = os.path.join(
            self.tempdir.name,
            str(self.itemgroup_id),
            '2016-02')
        self.assertTrue(os.path.exists(jan_path))
        self.assertTrue(os.path.exists(feb_path))

        jan_transactions = list(self.api.list_transactions(
            self.itemgroup_id,
            datetime.date(2016, 1, 1),
            datetime.date(2016, 1, 31)))
        first_quarter_transactions = list(self.api.list_transactions(
            self.itemgroup_id,
            datetime.date(2016, 1, 1),
            datetime.date(2016, 3, 31)))

        self.assertEqual(1, len(jan_transactions))
        self.assertDictEqual(
            json.loads(json_dumps(jan_movement)),
            json.loads(json_dumps(jan_transactions[0])))
        self.assertEqual(2, len(first_quarter_transactions))

    def test_get_current_quantity_aggregates_multiple_movements(self):
        self.api.bulk_save([
            self.make_movement(
                from_inv_id=None,
                to_inv_id=1,
                quantity=Decimal('10'),
                timestamp=datetime.datetime(2016, 1, 1, 9, 0, 0),
                type=InvMovementType.INGRESS),
            self.make_movement(
                from_inv_id=1,
                to_inv_id=2,
                quantity=Decimal('3.5'),
                timestamp=datetime.datetime(2016, 1, 2, 9, 0, 0),
                type=InvMovementType.TRANSFER),
            self.make_movement(
                from_inv_id=2,
                to_inv_id=None,
                quantity=Decimal('1.25'),
                timestamp=datetime.datetime(2016, 1, 3, 9, 0, 0),
                type=InvMovementType.EGRESS),
        ])

        self.assertDictEqual(
            {1: Decimal('6.5'), 2: Decimal('2.25')},
            dict(self.api.get_current_quantity(self.itemgroup_id)))

    def test_get_current_quantity_ignores_transactions_after_today(self):
        today = datetime.date.today()
        self.api.bulk_save([
            self.make_movement(
                from_inv_id=None,
                to_inv_id=1,
                quantity=Decimal('7'),
                timestamp=datetime.datetime.combine(
                    today - datetime.timedelta(days=1),
                    datetime.time(12, 0, 0)),
                type=InvMovementType.INGRESS),
            self.make_movement(
                from_inv_id=None,
                to_inv_id=1,
                quantity=Decimal('99'),
                timestamp=datetime.datetime.combine(
                    today + datetime.timedelta(days=1),
                    datetime.time(12, 0, 0)),
                type=InvMovementType.INGRESS),
        ])

        self.assertDictEqual(
            {1: Decimal('7')},
            dict(self.api.get_current_quantity(self.itemgroup_id)))

    def test_get_current_quantity_reads_all_history_without_snapshots(self):
        self.api.bulk_save([
            self.make_movement(
                from_inv_id=None,
                to_inv_id=1,
                quantity=Decimal('10'),
                timestamp=datetime.datetime(2016, 1, 1, 8, 0, 0),
                type=InvMovementType.INGRESS),
            self.make_movement(
                from_inv_id=1,
                to_inv_id=2,
                quantity=Decimal('4'),
                timestamp=datetime.datetime(2016, 1, 2, 8, 0, 0),
                type=InvMovementType.TRANSFER),
            self.make_movement(
                from_inv_id=2,
                to_inv_id=None,
                quantity=Decimal('1'),
                timestamp=datetime.datetime.combine(
                    datetime.date.today(),
                    datetime.time(10, 0, 0)),
                type=InvMovementType.EGRESS),
        ])

        self.assertDictEqual(
            {1: Decimal('6'), 2: Decimal('3')},
            dict(self.api.get_current_quantity(self.itemgroup_id)))

    def test_initial_movement_overrides_existing_quantity_for_inventory(self):
        self.api.bulk_save([
            self.make_movement(
                from_inv_id=None,
                to_inv_id=1,
                quantity=Decimal('10'),
                timestamp=datetime.datetime(2016, 1, 1, 8, 0, 0),
                type=InvMovementType.INGRESS),
            self.make_movement(
                from_inv_id=-1,
                to_inv_id=1,
                quantity=Decimal('4'),
                timestamp=datetime.datetime(2016, 1, 2, 8, 0, 0),
                type=InvMovementType.INITIAL),
        ])

        self.assertDictEqual(
            {1: Decimal('4')},
            dict(self.api.get_current_quantity(self.itemgroup_id)))

    def test_initial_movement_only_resets_target_inventory(self):
        self.api.bulk_save([
            self.make_movement(
                from_inv_id=None,
                to_inv_id=1,
                quantity=Decimal('10'),
                timestamp=datetime.datetime(2016, 1, 1, 8, 0, 0),
                type=InvMovementType.INGRESS),
            self.make_movement(
                from_inv_id=1,
                to_inv_id=2,
                quantity=Decimal('3'),
                timestamp=datetime.datetime(2016, 1, 2, 8, 0, 0),
                type=InvMovementType.TRANSFER),
            self.make_movement(
                from_inv_id=-1,
                to_inv_id=1,
                quantity=Decimal('5'),
                timestamp=datetime.datetime(2016, 1, 3, 8, 0, 0),
                type=InvMovementType.INITIAL),
        ])

        self.assertDictEqual(
            {1: Decimal('5'), 2: Decimal('3')},
            dict(self.api.get_current_quantity(self.itemgroup_id)))

    def test_initial_movement_overrides_prior_history(self):
        self.api.bulk_save([
            self.make_movement(
                from_inv_id=None,
                to_inv_id=1,
                quantity=Decimal('10'),
                timestamp=datetime.datetime(2016, 1, 1, 8, 0, 0),
                type=InvMovementType.INGRESS),
            self.make_movement(
                from_inv_id=1,
                to_inv_id=2,
                quantity=Decimal('4'),
                timestamp=datetime.datetime(2016, 1, 2, 8, 0, 0),
                type=InvMovementType.TRANSFER),
        ])
        self.api.save(self.make_movement(
            from_inv_id=-1,
            to_inv_id=2,
            quantity=Decimal('9'),
            timestamp=datetime.datetime(2016, 1, 3, 9, 0, 0),
            type=InvMovementType.INITIAL))

        self.assertDictEqual(
            {1: Decimal('6'), 2: Decimal('9')},
            dict(self.api.get_current_quantity(self.itemgroup_id)))


if __name__ == '__main__':
    unittest.main()
