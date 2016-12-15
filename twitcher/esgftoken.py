from OpenSSL import crypto
import base64
#import urllib
import requests

import logging
logger = logging.getLogger(__name__)


def get_certificate(url, access_token):
    # Generate a new key pair
    key_pair = crypto.PKey()
    key_pair.generate_key(crypto.TYPE_RSA, 2048)
    private_key = crypto.dump_privatekey(crypto.FILETYPE_PEM, key_pair).decode("utf-8")

    # Generate a certificate request using that key-pair
    cert_req = crypto.X509Req()

    # Create public key object
    cert_req.set_pubkey(key_pair)

    # Add the public key to the request
    cert_req.sign(key_pair, 'md5')

    der_cert_req = crypto.dump_certificate_request(crypto.FILETYPE_ASN1,
                                                   cert_req)

    encoded_cert_req = base64.b64encode(der_cert_req)

    headers = {}
    headers['Authorization'] = 'Bearer %s' % access_token
    #post_data = urllib.urlencode({'certificate_request': encoded_cert_req})
    post_data = {'certificate_request': encoded_cert_req}

    logger.debug(headers)
    logger.debug(post_data)

    r = requests.post(url,
                      headers=headers,
                      data=post_data,
                      verify=False)
    content = "{} {}".format(r.text, private_key)
    return content
