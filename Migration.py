"""
BMC Track-It! to JIRA Migration Script
Authors: Maxim Tam, Daniel Tremer
---
This script allows for work orders in BMC Track-It! Software to be easily
migrated over to JIRA via direct Track-It! Database access and JIRA REST API.
Various properties can be customized in this script via the config files but
the mapping of JIRA issues must still be customized per JIRA instance/project.
This also assumes the database schema for Track-It! is standardized. To run
this script, type the following in command prompt:
    python Migration.py support_config.json
"""
import json
import logging
import os
import sys
import time
import traceback
import urllib.parse
from datetime import datetime
from urllib.error import HTTPError

import pandas as pd
import requests
from pandas.tseries.offsets import BDay

import pymssql
import ssl


def post_request(jira_rest_call, data, jira_authorization):
    """
    Purpose:
        Submits POST request to create new ticket in JIRA and returns JSON
    Args:
        jira_rest_call (str): POST-able URL for JIRA
            Example: http://jira.org/rest/api/2/issue/
        data (str): JSON String in the format from get_database_cursor()
        jira_authorization (str): BASE64 Encoded Username:Password
    Returns:
        String of POST Request response. Should be acknowledgement of success or failure.
    """
    data = json.dumps(data).encode('utf8')
    headers = {"Authorization": jira_authorization,
               "Content-Type": "application/json"}
    response = requests.post(jira_rest_call, headers=headers, data=data)
    return response.json()


def get_request(jira_rest_call, jira_authorization):
    """
    @TODO Deprecate this and create a generic JIRA REST call via Requests
    Purpose:
        Submits GET request to JIRA and returns JSON
    Args:
        jira_rest_call (str): GET-able URL for JIRA
        jira_authorization (str): BASE64 Encoded Username:Password
    Returns:
        String of GET Request response. Should be in JSON format.
    """
    headers = {"Authorization": jira_authorization,
               "Content-Type": "application/json"}
    response = requests.get(jira_rest_call, headers=headers)
    return response.json()


def create_trackit_key(trackit_api_username, track_it_full_hostname):
    """
    Purpose:
        Submits GET request to Track-It! API for an authentication token
    Args:
        trackit_api_username (str): A Track-It! Technician ID
        track_it_full_hostname (str): Track-It! Server Address/URL
    Returns:
        Some key String that is used to authenticate a Track-It! API POST
    """
    url = "http://" + track_it_full_hostname + \
        "/TrackitWebAPI/api/Login?username=" + trackit_api_username + "&pwd="
    response = requests.get(url)
    return response.json()["data"]["apiKey"]


def post_close_request_trackit(trackit_key, workorder_id, jira_link, track_it_full_hostname):
    """
    Purpose:
        Submits POST request to close a Track-It! work order and sets
        the resolution as the link to the new JIRA ticket.
    Args:
        trackit_key (str): Track-It! Authorization key from create_trackit_key()
        workorder_id (int): Track-It! work order number
        jira_link (str): POST-able URL for JIRA
        track_it_full_hostname (url): Track-It! Server Address/URL
    Returns:
        Nothing. A String of POST Request response should be logged
        to the file specified in the config.
        Example: 2017-08-10 09:58:29,566 - INFO - [Migration.py:64] - Work Order 52204 updated successfully
    """
    url = "http://" + track_it_full_hostname + \
        "/TrackitWebAPI/api/workorder/Close/" + str(workorder_id)
    header = {"TrackItAPIKey": trackit_key, "Content-Type": "text/json"}
    text = "This workorder has been moved to \n" + str(jira_link) + ""
    response = requests.post(url, headers=header, data=json.dumps(text))
    if response.json()['success'] == 'false':
        logging.warning(
            "TrackIt workorder " + str(workorder_id) +
            " failed to close because: " + response.json()['data']['Message'])
    else:
        logging.info(response.json()['data']['message'])


def post_addnote_request_trackit(trackit_key, workorder_id, jira_link, track_it_full_hostname):
    """
    Purpose:
        Submits a POST request to add a note to the Track-It!
        work order with a link to the new JIRA ticket.
    Args:
        trackit_key (str): Track-It! Authorization key from create_trackit_key()
        workorder_id (int): Track-It! work order number
        jira_link (str): POST-able URL for JIRA
        track_it_full_hostname (url): Track-It! Server Address/URL
    Returns:
        Nothing.
    """
    url = "http://" + track_it_full_hostname + \
        "/TrackitWebAPI/api/workorder/AddNote/" + str(workorder_id)
    header = {"TrackItAPIKey": trackit_key, "Content-Type": "text/json"}
    text = "This workorder has been moved to \n" + str(jira_link) + ""
    data = {"IsPrivate": "false", "FullText": text, "ActivityCode": "Research"}
    response = requests.post(url, headers=header, data=json.dumps(data))


def get_database_cursor(db_connection, sql, jira_key):
    """
    Purpose:
        Connects to a database and retrieves a SQL query result.
        Parses the SQL query results into a JSON body valid for
        Jira/rest/api/2/issue POST request.
    Args:
        db_connection (pymssql Object): A very specific library object from
            pymssql-2.1.3-cp36-cp36m-win_amd64.whl which can connect to SQL
            Server 2008.
        sql (str): A very specific SQL Select statement.
        jira_key (str): JIRA Project key
    Returns:
        Array of JSON-format dictionary objects ready for POSTing to JIRA issues.
    """
    cursor = db_connection.cursor()
    cursor.execute(sql)
    database_full_output = []
    jira_issuetype = ""

    for row in cursor.fetchall():
        row = list(row)

        workorder_number = row[0]
        priority = row[1]
        request_date = row[2]
        summary = row[3]
        requester = row[4]
        assignee_username = row[5]
        due_date = row[6]
        modify_date = row[7]
        dept = row[8]
        wo_type = row[9]
        subtype = row[10]
        category = row[11]
        assigned_technician = row[12]
        description = row[13]
        notes = row[14]
        company = row[15]

        if priority == "Project":
            jira_issuetype = "Project"
        elif priority == "Ongoing Support":
            jira_issuetype = "Service Management"
        elif priority == "Change Request" and jira_key == "CRQ":
            jira_issuetype = "Change Request"
        else:
            jira_issuetype = "Incident Management"

        if subtype is not None:
            if len(subtype) > 0:
                subtype = subtype.replace(" ", "_")
        if category is not None:
            if len(category) > 0:
                category = category.replace(" ", "_")
        if company is not None:
            if len(company) > 0:
                company = company.replace(" ", "_")

        if priority == "Ongoing Support" or priority == "Change Request" or priority == "Project":
            priority = "Routine"
        if category is None:
            category = ""
        if dept is None:
            dept = ""
        if description is None:
            description = ""

        json_body = {
            "fields": {
                "project": {
                    "key": jira_key
                },
                "summary": summary,
                "description": description,
                "customfield_10411": int(workorder_number),
                "customfield_10420": request_date,
                "duedate": due_date,
                "customfield_11000": requester,
                "customfield_11701": [
                    dept
                ],
                "customfield_11900": [
                    subtype, category
                ],
                "customfield_11800": [
                    company
                ],
                "customfield_10300": {
                    "value": wo_type,
                    "id": "10302"
                },
                "issuetype": {
                    "name": jira_issuetype
                },
                "assignee": {
                    "key": assignee_username,
                    "name": assignee_username
                },
                "reporter": {
                    "key": "api",
                    "name": "api"
                },
                "priority": {
                    "name": priority
                }
            }
        }
        database_full_output.append(json_body)
    return database_full_output


def post_file_request(jira_rest_call, filepath, jira_authorization):
    """
    Purpose:
        Submits a POST request to JIRA to upload a file to an issue.
    Args:
        jira_rest_call (str): POST-able URL for a JIRA issue
        filepath (str): File path to a file (Less than 2GB)
        jira_authorization (str): BASE64 Encoded Username:Password
    Returns:
        Returns a POST response from JIRA acknowledging whether if it
        was a valid request.
    """
    headers = {"Authorization": jira_authorization,
               "X-Atlassian-Token": "nocheck"}
    files = {'file': open(filepath, 'rb')}
    response = requests.post(jira_rest_call, headers=headers, files=files)
    return response.text


def import_attachments(trackit_id, jira_rest_call, jira_authorization, attachment_folder):
    """
    Purpose:
        Loops through a file directory and uploads it to a JIRA issue.
    Args:
        trackit_id (int): Work order number from Track-It!
        jira_rest_call (str): POST-able URL for a JIRA issue
        jira_authorization (str): BASE64 Encoded Username:Password
        attachment_folder (str): Folder path to a specific work order's attachments
    Returns:
        Dictionary of attachments that have been uploaded.
    """
    trackit_dir = attachment_folder + '\\' + str(trackit_id)
    if os.path.isdir(trackit_dir):
        for file in os.listdir(trackit_dir):
            filepath = trackit_dir + '\\' + str(file)
            post_file_request(jira_rest_call, filepath, jira_authorization)

        return {trackit_id: os.listdir(trackit_dir)}


def mainloop(trackit_api_username,
             jira_rest_call_post,
             jira_rest_call_get_trackit_id,
             jira_authorization,
             db_connection,
             jira_key,
             track_it_full_hostname,
             jira_server_address,
             sql,
             attachment_folder,
             duedate_map):
    """
    Purpose:
        The main function to run everything above. From retrieving Track-It!
        data from the database to POSTing it to JIRA and closing Track-It!
        work orders with a comment to the new JIRA issue.
    Args:
        trackit_api_username (str): A Track-It! Technician ID
        jira_rest_call_post (str): POST-able URL for JIRA
        jira_rest_call_get_trackit_id (str): GET-able URL for JIRA
        jira_authorization (str): BASE64 Encoded Username:Password
        db_connection (pymssql Object): A very specific library object from
            pymssql-2.1.3-cp36-cp36m-win_amd64.whl which can connect to SQL
            Server 2008.
        jira_key (str): JIRA Project key
        track_it_full_hostname (str): Track-It! Server Address/URL
        jira_server_address (str): JIRA Server Address/URL
        sql (str): A very specific SQL Select statement.
        Example:
            use TRACKIT_DATA;
            SELECT wo_num 'Workorder Number',
            priority 'Priority',
            LEFT(CONVERT(VARCHAR, REQDATE, 120), 10) AS 'Request Date',
            task AS 'Summary',
            request 'Requestor',
            RESPONS AS 'Assignee Username',
            LEFT(CONVERT(VARCHAR, duedate, 120), 10) AS 'Due Date',
            LEFT(CONVERT(VARCHAR, modidate, 120), 10) AS 'Modify Date',
            TRACKIT_DATA.dbo.tasks.dept,
            type,
            wotype2 'Subtype',
            wotype3 'Category',
            respons 'Assigned Technician',
            descript 'Description',
            note 'Notes',
            lookup1 'Company'
            FROM TRACKIT_DATA.dbo.tasks
            WHERE tasks.respons in ('Maxim Tam')
            and priority in ('Ongoing Support','High','Urgent','Critical','Routine','Project')
            and WorkOrderStatusId = 1
            and reqdate >= '2017-07-11'
            ORDER BY RESPONS, WO_NUM DESC;
        attachment_folder (str): Folder path to a specific work order's attachments
        duedate_map (str): Dictionary of {Issue Priority:Resolution Days}
    Returns:
        Nothing.
    """
    # Declare database query output
    database_full_output = get_database_cursor(db_connection, sql, jira_key)
    print(datetime.now().strftime("%Y-%m-%d %H:%M:%S") +
          " Amount of open workorders: " + str(len(database_full_output)))
    # Cleans query output to create list of new Trackit workorder IDs
    # Retrieves all existing Jira Trackit IDs and compares the two lists
    trackit_ids_trackit = [int(x["fields"]["customfield_10411"])
                           for x in database_full_output]
    trackit_ids_jira_dict = dict(
        (get_request(jira_rest_call_get_trackit_id, jira_authorization)))
    trackit_ids_jira = [int(issue["fields"]["customfield_10411"])
                        for issue in trackit_ids_jira_dict["issues"] if
                        str(issue["fields"]["customfield_10411"]) != 'None']
    invalid_ids = [x for x in trackit_ids_trackit if x in trackit_ids_jira]
    database_full_output_valid = [x for x in database_full_output if
                                  int(x["fields"]["customfield_10411"]) not in invalid_ids]

    # Submits POST request to JIRA to create new issue
    # and closes & comments on the old Track-It! ticket
    if len(database_full_output_valid) > 0:
        for data in database_full_output_valid:

            print("Moving workorders to Jira:" +
                  str(data["fields"]["customfield_10411"]))
            logging.info("Moving workorders to Jira:" +
                         str(data["fields"]["customfield_10411"]))

            trackit_key = create_trackit_key(
                trackit_api_username, track_it_full_hostname=track_it_full_hostname)

            try:
                response = (post_request(
                    jira_rest_call_post, data, jira_authorization))
            except HTTPError:
                # replace customfield with data if you want the post request json string
                logging.error(
                    str(sys.exc_info()[1]) + ": " + str(data["fields"]["customfield_10411"]))
                continue

            # Jira URL to newly created ticket
            response = (response)
            jira_link = "http://" + jira_server_address + \
                "/browse/" + str(response["key"])
            jira_attachment_link = "http://" + jira_server_address + r"/rest/api/2/issue/" + str(
                response["key"]) + "/attachments"
            print(jira_attachment_link)
            logging.info("Successfully migrated to Jira at: " +
                         jira_attachment_link)
            import_attachments(data["fields"]["customfield_10411"],
                               jira_attachment_link, jira_authorization, attachment_folder)

            post_addnote_request_trackit(trackit_key,
                                         data["fields"]["customfield_10411"], jira_link,
                                         track_it_full_hostname)
            post_close_request_trackit(trackit_key, data["fields"]["customfield_10411"], jira_link,
                                       track_it_full_hostname)

    # Attempts to close TrackIt tickets when previously unable to
    if len(invalid_ids) > 0:
        print("Updating previously locked workorders: " + str(invalid_ids))
        for keys in invalid_ids:
            trackit_key = create_trackit_key(
                trackit_api_username, track_it_full_hostname)

            jira_trackit_id_url = "http://" + jira_server_address + \
                                  "/rest/api/2/search?jql=%22TrackIT%20%23%22%3D" + \
                str(keys)
            jira_link = "http://" + jira_server_address + "/browse/" \
                        + get_request(jira_trackit_id_url,
                                      jira_authorization)["issues"][0]["key"]

            post_addnote_request_trackit(
                trackit_key, keys, jira_link, track_it_full_hostname)
            post_close_request_trackit(
                trackit_key, keys, jira_link, track_it_full_hostname)

    # Due Date Creation
    # @TODO: PLEASE REFACTOR TO SHRINK MAINLOOP
    get_empty_duedates_url = "http://" + jira_server_address + \
        "/rest/api/2/search?jql=project%20%3D%20" \
        "" + jira_key + "" \
        "%20AND%20duedate%20is%20EMPTY%20AND%20type%20%20%3D%20%22Incident%20Management%22"

    duedates_response = get_request(get_empty_duedates_url, jira_authorization)
    srq_ids_empty = [[ticket["key"], ticket["fields"]["priority"]["name"],
                      pd.to_datetime(ticket["fields"]["created"][0:10])]
                     for ticket in duedates_response["issues"]]

    for value in srq_ids_empty:
        duedate = str(value[2] + BDay(duedate_map[str(value[1])]))[0:10]
        headers = {"Authorization": "Basic YXBpOlBhc3N3b3Jk",
                   "Content-Type": "application/json"}

        r = requests.put('http://' + config["jira_server_address"] + \
                         '/rest/api/2/issue/' + str(value[0]),
                         data=json.dumps({"fields": {"duedate": str(duedate)}}), headers=headers)


if __name__ == "__main__":

    with open(sys.argv[1]) as json_data:
        config = json.load(json_data)

    jira_rest_call_post = "http://" + \
        config["jira_server_address"] + "/rest/api/2/issue/"

    jira_rest_call_get_trackit_id = "http://" + config["jira_server_address"] + \
        "/rest/api/2/search?jql=project%20%3D%20%22" + config["jira_fields"]["project"]["key"] + \
        "%22&fields=customfield_10411&maxResults=1000"


    logging.basicConfig(filename=config["log_file"], level=logging.DEBUG,
                        format='%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s')

    while True:

        try:
            db_connection = pymssql.connect(
                host=config["database_cnf"]["host"],
                user=config["database_cnf"]["user"],
                password=config["database_cnf"]["password"],
                database=config["database_cnf"]["database"]
            )

            mainloop(trackit_api_username=config["trackit_api_username"],
                     jira_rest_call_post=jira_rest_call_post,
                     jira_rest_call_get_trackit_id=jira_rest_call_get_trackit_id,
                     jira_authorization=config["jira_authorization"],
                     db_connection=db_connection,
                     jira_key=config["jira_fields"]["project"]["key"],
                     track_it_full_hostname=config["trackIT_server_address"],
                     jira_server_address=config["jira_server_address"],
                     sql=config["sql"],
                     attachment_folder=config["attachment_folder"],
                     duedate_map=config["ticket_duetime_mapping_days"])
        except Exception as e:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            with open(config["traceback_file"], 'w') as traceback_file:
                traceback.print_exception(
                    exc_type, exc_value, exc_traceback, limit=3, file=traceback_file)
            logging.error(
                "Unknown Error, see traceback file: " + str(sys.exc_info()))

        time.sleep(60)
