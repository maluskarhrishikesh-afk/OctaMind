import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import src.email.gmail_service as gmail_service_mod


def _make_client(service=None):
    service = service or MagicMock()
    with patch.object(gmail_service_mod, "get_gmail_service", return_value=service):
        client = gmail_service_mod.GmailServiceClient()
    return client, service


class TestCreateSmartLabelRule:
    def test_creates_gmail_filter_for_future_emails(self):
        client, service = _make_client()
        client.create_label = MagicMock(return_value={
            "status": "success",
            "label_id": "LBL1",
            "label_name": "Hrishikesh Zoho",
        })

        service.users.return_value.messages.return_value.list.return_value.execute.return_value = {
            "messages": [{"id": "m1"}, {"id": "m2"}]
        }
        service.users.return_value.settings.return_value.filters.return_value.list.return_value.execute.return_value = {
            "filter": []
        }
        service.users.return_value.settings.return_value.filters.return_value.create.return_value.execute.return_value = {
            "id": "FILTER1"
        }

        result = client.create_smart_label_rule(
            label_name="Hrishikesh Zoho",
            from_email="hrishikesh.maluskar@zohomail.in",
            also_archive=True,
        )

        assert result["status"] == "success"
        assert result["filter_id"] == "FILTER1"
        assert result["future_rule_created"] is True

        batch_modify_body = service.users.return_value.messages.return_value.batchModify.call_args.kwargs["body"]
        assert batch_modify_body["addLabelIds"] == ["LBL1"]
        assert batch_modify_body["removeLabelIds"] == ["INBOX"]

        filter_body = service.users.return_value.settings.return_value.filters.return_value.create.call_args.kwargs["body"]
        assert filter_body["criteria"] == {"from": "hrishikesh.maluskar@zohomail.in"}
        assert filter_body["action"]["addLabelIds"] == ["LBL1"]
        assert filter_body["action"]["removeLabelIds"] == ["INBOX"]

    def test_reuses_matching_existing_filter(self):
        client, service = _make_client()
        client.create_label = MagicMock(return_value={
            "status": "success",
            "label_id": "LBL1",
            "label_name": "Hrishikesh Zoho",
        })

        service.users.return_value.messages.return_value.list.return_value.execute.return_value = {
            "messages": []
        }
        service.users.return_value.settings.return_value.filters.return_value.list.return_value.execute.return_value = {
            "filter": [
                {
                    "id": "FILTER_EXISTING",
                    "criteria": {"from": "hrishikesh.maluskar@zohomail.in"},
                    "action": {"addLabelIds": ["LBL1"]},
                }
            ]
        }

        result = client.create_smart_label_rule(
            label_name="Hrishikesh Zoho",
            from_email="hrishikesh.maluskar@zohomail.in",
        )

        assert result["status"] == "success"
        assert result["filter_id"] == "FILTER_EXISTING"
        assert result["future_rule_created"] is False
        assert service.users.return_value.settings.return_value.filters.return_value.create.call_count == 0

    def test_returns_error_if_filter_creation_fails(self):
        client, service = _make_client()
        client.create_label = MagicMock(return_value={
            "status": "success",
            "label_id": "LBL1",
            "label_name": "Hrishikesh Zoho",
        })

        service.users.return_value.messages.return_value.list.return_value.execute.return_value = {
            "messages": [{"id": "m1"}]
        }
        service.users.return_value.settings.return_value.filters.return_value.list.return_value.execute.return_value = {
            "filter": []
        }
        service.users.return_value.settings.return_value.filters.return_value.create.return_value.execute.side_effect = Exception(
            "insufficient authentication scopes"
        )

        result = client.create_smart_label_rule(
            label_name="Hrishikesh Zoho",
            from_email="hrishikesh.maluskar@zohomail.in",
        )

        assert result["status"] == "error"
        assert result["emails_labeled"] == 1
        assert result["future_rule_created"] is False
        assert "could not create the Gmail filter" in result["message"]


class TestDeleteSmartLabelRule:
    def test_deletes_matching_filters_by_sender(self):
        client, service = _make_client()
        service.users.return_value.settings.return_value.filters.return_value.list.return_value.execute.return_value = {
            "filter": [
                {
                    "id": "FILTER1",
                    "criteria": {"from": "hrishikesh.maluskar@zohomail.in"},
                    "action": {"addLabelIds": ["LBL1"]},
                },
                {
                    "id": "FILTER2",
                    "criteria": {"from": "other@example.com"},
                    "action": {"addLabelIds": ["LBL2"]},
                },
            ]
        }

        result = client.delete_smart_label_rule(
            from_email="hrishikesh.maluskar@zohomail.in",
        )

        assert result["status"] == "success"
        assert result["filters_deleted"] == 1
        assert result["deleted_filter_ids"] == ["FILTER1"]
        delete_call = service.users.return_value.settings.return_value.filters.return_value.delete.call_args
        assert delete_call.kwargs["id"] == "FILTER1"

    def test_deletes_matching_filters_by_label_name(self):
        client, service = _make_client()
        service.users.return_value.labels.return_value.list.return_value.execute.return_value = {
            "labels": [
                {"id": "LBL1", "name": "Hrishikesh Zoho"},
            ]
        }
        service.users.return_value.settings.return_value.filters.return_value.list.return_value.execute.return_value = {
            "filter": [
                {
                    "id": "FILTER1",
                    "criteria": {"from": "hrishikesh.maluskar@zohomail.in"},
                    "action": {"addLabelIds": ["LBL1"]},
                }
            ]
        }

        result = client.delete_smart_label_rule(label_name="Hrishikesh Zoho")

        assert result["status"] == "success"
        assert result["filters_deleted"] == 1

    def test_returns_success_when_no_matching_filters_exist(self):
        client, service = _make_client()
        service.users.return_value.settings.return_value.filters.return_value.list.return_value.execute.return_value = {
            "filter": []
        }

        result = client.delete_smart_label_rule(
            from_email="hrishikesh.maluskar@zohomail.in",
        )

        assert result["status"] == "success"
        assert result["filters_deleted"] == 0
        assert service.users.return_value.settings.return_value.filters.return_value.delete.call_count == 0


class TestDeleteAllFiltersAndLabels:
    def test_deletes_all_filters_and_custom_labels(self):
        client, service = _make_client()
        service.users.return_value.settings.return_value.filters.return_value.list.return_value.execute.return_value = {
            "filter": [
                {"id": "FILTER1"},
                {"id": "FILTER2"},
            ]
        }
        service.users.return_value.labels.return_value.list.return_value.execute.return_value = {
            "labels": [
                {"id": "INBOX", "name": "INBOX", "type": "system"},
                {"id": "LBL1", "name": "Temporary", "type": "user"},
                {"id": "LBL2", "name": "Hrishikesh Zoho", "type": "user"},
            ]
        }

        result = client.delete_all_filters_and_labels()

        assert result["status"] == "success"
        assert result["filters_deleted"] == 2
        assert result["labels_deleted"] == 2
        assert result["deleted_filter_ids"] == ["FILTER1", "FILTER2"]
        assert result["deleted_label_ids"] == ["LBL1", "LBL2"]
        assert result["deleted_label_names"] == ["Temporary", "Hrishikesh Zoho"]

        deleted_filter_ids = [
            call.kwargs["id"]
            for call in service.users.return_value.settings.return_value.filters.return_value.delete.call_args_list
        ]
        deleted_label_ids = [
            call.kwargs["id"]
            for call in service.users.return_value.labels.return_value.delete.call_args_list
        ]
        assert deleted_filter_ids == ["FILTER1", "FILTER2"]
        assert deleted_label_ids == ["LBL1", "LBL2"]

    def test_returns_success_when_no_filters_or_custom_labels_exist(self):
        client, service = _make_client()
        service.users.return_value.settings.return_value.filters.return_value.list.return_value.execute.return_value = {
            "filter": []
        }
        service.users.return_value.labels.return_value.list.return_value.execute.return_value = {
            "labels": [
                {"id": "INBOX", "name": "INBOX", "type": "system"},
                {"id": "TRASH", "name": "TRASH", "type": "system"},
            ]
        }

        result = client.delete_all_filters_and_labels()

        assert result["status"] == "success"
        assert result["filters_deleted"] == 0
        assert result["labels_deleted"] == 0
        assert service.users.return_value.settings.return_value.filters.return_value.delete.call_count == 0
        assert service.users.return_value.labels.return_value.delete.call_count == 0


class TestListAllFiltersAndLabels:
    def test_lists_filters_and_partitions_user_and_system_labels(self):
        client, service = _make_client()
        service.users.return_value.settings.return_value.filters.return_value.list.return_value.execute.return_value = {
            "filter": [
                {
                    "id": "FILTER1",
                    "criteria": {"from": "boss@example.com", "subject": "Invoice"},
                    "action": {"addLabelIds": ["LBL1"], "removeLabelIds": ["INBOX"]},
                }
            ]
        }
        service.users.return_value.labels.return_value.list.return_value.execute.return_value = {
            "labels": [
                {"id": "INBOX", "name": "INBOX", "type": "system"},
                {"id": "LBL1", "name": "Finance", "type": "user"},
            ]
        }

        result = client.list_all_filters_and_labels()

        assert result["status"] == "success"
        assert result["filters_count"] == 1
        assert result["user_labels_count"] == 1
        assert result["system_labels_count"] == 1
        assert result["filters"][0]["from"] == "boss@example.com"
        assert result["filters"][0]["subject"] == "Invoice"
        assert result["user_labels"][0]["name"] == "Finance"
        assert result["system_labels"][0]["name"] == "INBOX"


class TestArchiveAllMatchingEmails:
    def test_archives_all_batches_until_query_is_exhausted(self):
        client, service = _make_client()
        service.users.return_value.messages.return_value.list.return_value.execute.side_effect = [
            {"messages": [{"id": "m1"}, {"id": "m2"}]},
            {"messages": [{"id": "m3"}]},
            {"messages": []},
        ]

        result = client.archive_all_matching_emails("category:promotions in:inbox", batch_size=2)

        assert result["status"] == "success"
        assert result["archived_count"] == 3
        assert result["batches_processed"] == 2
        batch_modify_calls = service.users.return_value.messages.return_value.batchModify.call_args_list
        assert len(batch_modify_calls) == 2
        assert batch_modify_calls[0].kwargs["body"]["ids"] == ["m1", "m2"]
        assert batch_modify_calls[1].kwargs["body"]["ids"] == ["m3"]


class TestDeleteAllFilters:
    def test_deletes_all_filters_and_preserves_labels(self):
        client, service = _make_client()
        service.users.return_value.settings.return_value.filters.return_value.list.return_value.execute.return_value = {
            "filter": [{"id": "FILTER1"}, {"id": "FILTER2"}]
        }

        result = client.delete_all_filters()

        assert result["status"] == "success"
        assert result["filters_deleted"] == 2
        assert result["deleted_filter_ids"] == ["FILTER1", "FILTER2"]
        assert service.users.return_value.settings.return_value.filters.return_value.delete.call_count == 2
        assert service.users.return_value.labels.return_value.delete.call_count == 0
