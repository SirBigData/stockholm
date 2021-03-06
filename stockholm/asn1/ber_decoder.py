# -*- coding: utf-8 -*-
import logging
import struct

log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())


def tag_type_decode(byte_string):
    """
    Decode tge tag type from the 6th bit of the first octet.
    Return 0 if it's Primitive or 1 if it's Constructed.
    :param byte_string: string of bytes
    :return: int
    """
    first_octet = ord(byte_string[0])
    return int(first_octet & 32 == 32)


def tag_identifier_decode(byte_string):
    """
    Return the tag number and the number of identifier header_octets.
    :param byte_string: string of bytes
    :return: (int, int)
    """
    identifier_octets = 0
    first_octet = ord(byte_string[0])
    if first_octet & 31 == 31:  # long format Tag (first 5 bits are 1)
        number, identifier_octets = lvq_decode(byte_string[1:])
    else:  # short format Tag
        number = first_octet - (first_octet & 224)
    identifier_octets += 1
    return number, identifier_octets


def lvq_decode(byte_string):
    """
    Return the value of the byte string in base 128, and the number of header_octets.
    :param byte_string: string of bytes
    :return: (int, int)
    """
    values = []
    result = 0
    size = 0
    while True:
        b = ord(byte_string[size:size+1])  # get decimal value
        size += 1
        values.append((b & 0x7f))  # add to list the value with out the 8th bit
        if b & 0x80 == 0:  # it has 0 in the 8th bit exit the loop
            break
    shift = 7 * (len(values) - 1)  # how many shifts I must do
    for i in values:
        i << shift
        result |= i
        shift - 7
    return result, size


def long_format_length_decode(byte_string):
    length = 0
    number_of_octets = len(byte_string)
    shift = 8 * (number_of_octets - 1)
    for i in range(number_of_octets):
        length |= ord(byte_string[i]) << shift
        shift -= 8
    return length


def get_bit(number, index):
    """
    Return the bit at index position (starts from 0) from the number in base 2.
    :param number: int
    :param index: int
    :return: int
    """
    return int((number & (1 << index)) != 0)


class Header(object):

    def __init__(self, byte_string):
        self.type = tag_type_decode(byte_string)
        self.number, self.identifier_octets = tag_identifier_decode(byte_string)
        self.octets = 0
        self.length_octets = 0
        self.data_length = 0
        self.total_octets = 0
        self.extra_data_length = 0
        self.length_decode(byte_string)

    def __repr__(self):
        return "Type:{0.type} Number:{0.number} HeaderOctets:{0.octets} DataLength: {0.data_length}".format(self)

    def length_decode(self, byte_string):
        first_octet = ord(byte_string[self.identifier_octets])
        if first_octet == 128:  # Indefinite size
            self.length_octets = 1
            self.octets = self.identifier_octets + self.length_octets
            self.extra_data_length = len(byte_string) - self.octets
        else:  # definite size
            if first_octet & 128 == 128:  # long format
                number_of_extra_length_octets = first_octet - 128
                self.length_octets = 1 + number_of_extra_length_octets
                self.octets = self.identifier_octets + self.length_octets  # The offset of header_octets to read the content
                index = self.identifier_octets + 1
                self.data_length = long_format_length_decode(byte_string[index:index + number_of_extra_length_octets])
                self.extra_data_length = 0
            else:  # short format
                self.length_octets = 1
                self.octets = self.identifier_octets + self.length_octets
                self.data_length = first_octet
                self.extra_data_length = len(byte_string) - self.octets - self.data_length
        self.total_octets = self.octets + self.data_length


class Tag(object):
    """
    Representation of an asn1 tag.
    :param byte_string: string of bytes
    """
    _type_name = ('primitive', 'constructed')

    def __init__(self, header=None, byte_string=None, load_value=True, name=None):
        self.header = header
        self.value = None
        self.nested_tags = ()
        self.load_value = load_value
        self.name = name
        if byte_string:
            self.decode(byte_string)

    def __repr__(self):
        if self.header.type == 0:
            if self.name:
                return "[{0.name} ({0.number})] - {0.value}".format(self)
            else:
                return "[{0.header.number:<3}] - {0.value}".format(self)
        elif self.header.type == 1:
            if self.nested_tags:
                return "[{0:<3}]\n\t{1}".format(self.header.number, "\n\t".join((str(x) for x in self.nested_tags)))
            else:
                return "Tag(number={0.header.number})(type={0.get_type})(header length={0.header.octets}" \
                       "[identifier={0.header.identifier_octets}, length={0.header.length_octets}])" \
                       "(data length={0.header.data_length})(extra data={0.header.extra_data_length})".format(self)

    def decode(self, byte_string):
        """
        Decode the Tag type, number and number of the Tag identifiers header_octets.
        :param byte_string: string of bytes
        """
        if not self.header:
            self.header = Header(byte_string)
        if self.load_value:
            if self.header.type == 0:
                self.decode_primitive(byte_string)
            elif self.header.type == 1:
                self.decode_constructed(byte_string)

    @property
    def number(self):
        return self.header.number

    @property
    def type(self):
        return self.header.type

    @property
    def header_octets(self):
        return self.header.octets

    @property
    def total_octets(self):
        return self.header.total_octets

    @property
    def data_length(self):
        return self.header.data_length

    @property
    def get_type(self):
        """
        Return the name of the Tag type.

        :return: str
        """
        type_name = Tag._type_name[self.header.type]
        if self.header.data_length == 0:
            type_name = "{}-Indefinite".format(type_name)
        return type_name

    def decode_constructed(self, byte_string):
        self.value = byte_string[self.header.octets:self.header.total_octets]

    def decode_primitive(self, byte_string):
        self.value = self.decode_value(byte_string[self.header.octets:self.header.total_octets])

    def decode_value(self, byte_string):
        """
        Base implementation of how decode the value, it cant be over writen to modify the encoding.
        :param byte_string: string of bytes
        :return: str
        """
        return byte_string.encode('hex')

    def add_nested_tag(self, tag):
        item = (tag,)
        if self.header.type == 1:
            self.nested_tags += (tag,)