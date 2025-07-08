# Copyright (c) Istituto Nazionale di Fisica Nucleare (INFN). 2019-2025
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import enum


def nullorempty(value):
    return True if value is None or value == "" or value == "None" else False


def notnullorempty(value):
    return not nullorempty(value)


def defaulttoempty(value):
    return value if value is not None else ""


def enum_to_string(obj):
    """
    Convert an Enum member to its string representation (name).

    This function is used to extract the string representation (name) of an Enum
    member. If the input is not an Enum member, the input is returned as is,
    allowing Jinja or other template engines to use their default behavior.

    Args:
        obj: An object that may be an Enum member or any other type.

    Returns:
        str or obj: If `obj` is an Enum member, its name (a string) is returned.
                    If `obj` is not an Enum member, `obj` is returned unchanged.
    """
    if isinstance(obj, enum.Enum):
        return obj.name
    # For all other types, let Jinja use default behavior
    return obj


def str2bool(s):
    """
    Convert a string representation of a boolean to a boolean value.

    This function takes a string 's' and converts it to a boolean value. The conversion
    is case-insensitive and considers values like 'yes', '1', and 'true' as True, while
    values like 'no', '0', and 'false' are considered as False.

    Args:
        s (str): A string representing a boolean value.

    Returns:
        bool: True if 's' represents a truthy value, False otherwise.
    """
    return s.lower() in ["yes", "1", "true"]

def xstr(s):
    """
    Convert a value to a string or return an empty string if the value is None.

    This function takes a value 's' and converts it to a string representation if
    's' is not None. If 's' is None, it returns an empty string.

    Args:
        s: Any value that can be converted to a string.

    Returns:
        str: A string representation of 's' if 's' is not None, or an empty string.
    """
    return "" if s is None else str(s)


def nnstr(s):
    """
    Convert a value to a string or return an empty string if the value is None or empty.

    This function takes a value 's' and converts it to a string representation if 's'
    is not None and not an empty string. If 's' is None or an empty string, it returns
    an empty string.

    Args:
        s: Any value that can be converted to a string.

    Returns:
        str: A string representation of 's' if 's' is not None and not an empty string,
             or an empty string.
    """
    return "" if (s is None or s == "") else str(s)
