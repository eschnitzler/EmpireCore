"""A monument's or laboratory's progress: glp for a laboratory, gmp for a monument."""

from __future__ import annotations

import pytest

from empire_core.castle import (
    GetLaboratoryProgressRequest,
    GetMonumentProgressRequest,
    LaboratoryProgressResponse,
    LandmarkProgress,
    MonumentProgressResponse,
)
from empire_core.enums import MapItemType
from empire_core.map import MapAreaItem
from empire_core.protocol.base import parse_response
from tests.service_helpers import conn, make_client, xt_packet

LABORATORY = MapAreaItem.from_list([MapItemType.LABORATORY, 10, 20, 7001, 4001, 3, 0, -1, "Lab"])
MONUMENT = MapAreaItem.from_list([MapItemType.MONUMENT, 10, 20, 7002, 4001, 0, 2, 0, -1, "Monument"])


def test_the_requests_send_the_object_id():
    assert GetLaboratoryProgressRequest(object_id=7001).to_payload() == {"ID": 7001}
    assert GetMonumentProgressRequest(object_id=7002).to_payload() == {"ID": 7002}


@pytest.mark.parametrize(("command", "model"), [("glp", LaboratoryProgressResponse), ("gmp", MonumentProgressResponse)])
def test_the_reply_reads_the_object_and_its_points(command, model):
    reply = parse_response(command, {"OID": 7001, "CP": 1250})

    assert type(reply) is model and isinstance(reply, LandmarkProgress)
    assert (reply.object_id, reply.points) == (7001, 1250)


@pytest.mark.parametrize(("landmark", "command"), [(LABORATORY, "glp"), (MONUMENT, "gmp")])
def test_the_landmark_type_picks_the_command(landmark, command):
    client = make_client({command: xt_packet(command, {"OID": landmark.location_id, "CP": 1250})})

    progress = client.castle.get_landmark_progress(landmark)

    assert conn(client).request_payloads == [(command, {"ID": landmark.location_id})]
    assert progress.points == 1250


def test_another_area_type_is_refused():
    castle = MapAreaItem.from_list([MapItemType.CASTLE, 10, 20])
    client = make_client()

    with pytest.raises(ValueError):
        client.castle.get_landmark_progress(castle)

    assert conn(client).requested == []
