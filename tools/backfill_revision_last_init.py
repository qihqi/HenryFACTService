import argparse
import sys
from collections import defaultdict

from henry.config import revisionapi
from henry.coreconfig import transactionapi
from henry.product.dao import InvMovementType


def backfill_revision_last_init(revision_id: int) -> int:
    with revisionapi.db_session:
        revision = revisionapi.get_doc(revision_id)
        if revision is None:
            print('Revision {} not found'.format(revision_id), file=sys.stderr)
            return 1

        if revision.meta is None or revision.meta.timestamp is None:
            print(
                'Revision {} is missing timestamp metadata'.format(revision_id),
                file=sys.stderr)
            return 1

        movements_by_itemgroup = defaultdict(set)
        for movement in revision.items_to_transaction(revisionapi.dbapi):
            if movement.type != InvMovementType.INITIAL:
                continue
            if movement.itemgroup_id is None or movement.to_inv_id is None:
                continue
            movements_by_itemgroup[movement.itemgroup_id].add(
                movement.to_inv_id)

        if not movements_by_itemgroup:
            print(
                'Revision {} produced no INITIAL movements'.format(revision_id))
            return 0

        revision_date = revision.meta.timestamp.date()
        for itemgroup_id, inventory_ids in sorted(movements_by_itemgroup.items()):
            transactionapi._update_init_dates(
                itemgroup_id,
                revision_date,
                sorted(inventory_ids))
            print(
                'updated itemgroup {} inventories {} to {}'.format(
                    itemgroup_id,
                    sorted(inventory_ids),
                    revision_date.isoformat()))

    return 0


def main():
    parser = argparse.ArgumentParser(
        description='Backfill __last_init metadata for an existing revision.')
    parser.add_argument('revision_id', type=int, help='Revision metadata id')
    args = parser.parse_args()
    raise SystemExit(backfill_revision_last_init(args.revision_id))


if __name__ == '__main__':
    main()
