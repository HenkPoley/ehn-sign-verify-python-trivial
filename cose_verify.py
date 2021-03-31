#!env python3.8

import argparse
import json
import sys
import zlib

from base64 import b64decode
from base45 import b45decode

import cbor2
from binascii import unhexlify, hexlify

from cose.algorithms import Es256
from cose.curves import P256
from cose.algorithms import Es256, EdDSA
from cose.headers import KID
from cose.keys import CoseKey
from cose.keys.keyparam import KpAlg, EC2KpX, EC2KpY, EC2KpCurve
from cose.keys.keyparam import KpKty
from cose.keys.keytype import KtyEC2
from cose.messages import CoseMessage
from cryptography import x509
from cryptography.hazmat.primitives import hashes

parser = argparse.ArgumentParser(
    description="Parse and validate a base45/zlib/cose/cbor QR."
)
parser.add_argument(
    "-B", "--base64", action="store_true", help="Use base64 instead of base45"
)
parser.add_argument(
    "-b", "--skip-base45", action="store_true", help="Skip base45 decoding"
)
parser.add_argument(
    "-z", "--skip-zlib", action="store_true", help="Skip zlib decompression"
)
parser.add_argument(
    "-i",
    "--ignore-signature",
    action="store_true",
    help="Ignore the signature, do not validate",
)
parser.add_argument(
    "-c",
    "--skip-cbor",
    action="store_true",
    help="Skip CBOR unpacking (accept any UTF8)",
)
parser.add_argument(
    "-p",
    "--prettyprint-json",
    action="store_true",
    help="Pretty print and sort the JSON",
)
parser.add_argument(
    "cert", default="dsc-worker.pem", nargs="?", help="Certificate to validate against"
)
args = parser.parse_args()

cin = sys.stdin.buffer.read()

if args.base64:
    cin = b64decode(cin.decode("ASCII"))
else:
    if not args.skip_base45:
        cin = b45decode(cin.decode("ASCII"))
if not args.skip_zlib:
    cin = zlib.decompress(cin)

decoded = CoseMessage.decode(cin)

if not args.ignore_signature:
    with open(args.cert, "rb") as file:
        pem = file.read()
    cert = x509.load_pem_x509_certificate(pem)
    pub = cert.public_key().public_numbers()

    fingerprint = cert.fingerprint(hashes.SHA256())
    # keyid = fingerprint[-8:]
    keyid = fingerprint[0:8]

    given_kid = None
    if KID in decoded.phdr.keys():
        given_kid = decoded.phdr[KID]
    else:
        given_kid = decoded.uhdr[KID]

    if given_kid != keyid:
        raise Exception(
            "KeyID is unknown (expected %s, got %s) -- cannot verify."
            % (hexlify(keyid), hexlify(given_kid))
        )

    decoded.key = CoseKey.from_dict(
        {
            KpKty: KtyEC2,
            EC2KpCurve: P256,  # Ought o be pk.curve - but the two libs clash
            KpAlg: Es256,  # ecdsa-with-SHA256
            EC2KpX: pub.x.to_bytes(32, byteorder="big"),
            EC2KpY: pub.y.to_bytes(32, byteorder="big"),
        }
    )

    if not decoded.verify_signature():
        raise Exception("faulty sig")

payload = decoded.payload

if not args.skip_cbor:
    payload = cbor2.loads(payload)
    if args.prettyprint_json:
        payload = print(json.dumps(payload, indent=4, sort_keys=True))
    else:
        payload = json.dumps(payload)
    print(payload)
    sys.exit(0)

sys.stdout.buffer.write(payload)
