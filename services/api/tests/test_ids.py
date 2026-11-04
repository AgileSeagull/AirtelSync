from app.data_store import gstin_registry, leads, udyam_registry
from app.ids import gstin, udyam


def test_every_registry_gstin_passes_format_and_checksum():
    bad = [g for g in gstin_registry() if not gstin.validate(g).valid]
    assert bad == []


def test_lead_gstins_pass():
    assert all(gstin.validate(r["gstin"]).valid for r in leads() if r["has_gstin"] == "Y")


def test_single_character_typo_is_caught():
    g = next(iter(gstin_registry()))
    for i in range(15):
        ch = "A" if g[i] != "A" else "B"
        if i < 2 or 7 <= i <= 10:
            ch = "1" if g[i] != "1" else "2"
        mutated = g[:i] + ch + g[i + 1:]
        assert not gstin.validate(mutated).valid, (i, mutated)


def test_state_code_and_pan_extracted():
    c = gstin.validate("32TTNXB7384T1ZW")
    assert c.valid and c.state == "Kerala" and c.pan == "TTNXB7384T"


def test_gstin_length_and_lowercase_input():
    assert not gstin.validate("32TTNXB7384T1Z").valid
    assert gstin.validate(" 32ttnxb7384t1zw ").valid


def test_mask_gstin():
    assert gstin.mask("32TTNXB7384T1ZW") == "32TTN•••••••1ZW"


def test_every_udyam_number_is_well_formed():
    assert all(udyam.validate(n).valid for n in udyam_registry())
    assert not udyam.validate("UDYAM-XX-00-1234567").valid
    assert not udyam.validate("UDYAM-KL-00-123").valid
