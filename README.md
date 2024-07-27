# Helix DAM Text Thumbnail Webhook

This repository contains a webhook service for creating small thumbnails with syntax highlighting for various types of text files in Perforce Helix DAM.

## Prerequisites

- Docker installed on your server
- Git (for pulling updates)
- Access to your Helix DAM instance
- Account key for Helix DAM API access

## Installation
This is simplest to install directly on your DAM (Teamhub) instance so no traffic needs to go over the public internet.

1. Clone the repository:
   ```
   git clone https://github.com/jase-perf/helix-dam-text-thumbnail-webhook.git
   cd helix-dam-text-thumbnail-webhook
   ```
2. Make sure that `start_container.sh` and `update_and_build.sh` are executable:
   ```
   chmod +x start_container.sh update_and_build.sh
   ```
3. Build the Docker image:
   ```
   ./update_and_build.sh
   ```

4. Edit the `start_container.sh` script:
   - Replace `http://10.0.0.1` with your actual DAM private IP or URL (If you are running this on the same instance then the private IP is preferred. If running on an external server, then using a public https endpoint will be more secure.)
   - Replace `your_account_key_here` with your Helix DAM account API key:
     - As an admin in DAM, click on in the upper right menu and choose `Go to Helix Teamhub`
     - Click on the small arrow in the upper right by your profile image and select `User Preferences`
     - Select API Keys
     - Click `+ Add new key` at the bottom, give it a title, and click save
     - Now copy the API key that was generated and paste it into the `start_container.sh` file.
   - If you have other webhook containers running on this machine, be sure to change the port value in the start_container.sh file to route to a different value.
     - For example, change `-p 8080:8080 \` to `-p 8181:8080 \` to serve the app on port 8181 instead. (Keep the number after the colon set to 8080)

5. Start the container:
   ```
   ./start_container.sh
   ```

6. Setup the webhook on DAM
   - As an admin in DAM, click on in the upper right menu and choose `Go to Helix Teamhub`
   - Select `Webhooks` from the left hand menu
   - Click the + button to add a new webhook
   - Give it a name and customize any settings you want (the defaults should work if you want this to apply to all projects in DAM)
   - Click Next and enter the URL or IP address of the docker container's instance followed by `/webhook`. If running on the same instance as DAM, then `http://localhost:8080/webhook` should work. (If you modified your port value, be sure to put the modified number.) Then click Save.
     - By default it will attempt to generate thumbnails for any file extension that is recognized by [Pygments Lexer](https://pygments.org/docs/lexers/), which is thousands of file extensions. If you want to limit this to specific file extensions, look into [Restricting when webhooks run](https://help.perforce.com/helix-core/helix-dam/current/Content/HelixDAM-User/adding-webhooks.html#restrictions) in the Helix DAM User Guide.

The webhook service is now running and will process text files added to your DAM instance.

See instructions below on **Tailing Logs** to view the logs and confirm that webhook requests are being received successfully.

## Updating

To update the service with the latest changes:

1. Pull the latest changes and rebuild the Docker image:
   ```
   ./update_and_build.sh
   ```

2. Restart the container:
   ```
   ./start_container.sh
   ```

## Configuration

The service runs on port 8080 by default. If you need to change this, modify the `-p 8080:8080` line in `start_container.sh` to your desired port.


## Troubleshooting and Monitoring

### Viewing Logs
To view the logs of the container:

```bash
docker logs text-thumbnail-webhook
```

This will display all logs from the container start.

### Tailing Logs
To continuously watch the logs in real-time:

```bash
docker logs -f text-thumbnail-webhook
```

This command will follow the log output, displaying new log entries as they occur. Press Ctrl+C to stop watching the logs.

### Viewing Recent Logs
To view only the most recent logs:

```bash
docker logs --tail 100 text-thumbnail-webhook
```

This will show the last 100 log entries. Adjust the number as needed.

### Sending logs to AWS Cloudwatch
Docker has a built-in log processor for AWS cloudwatch, which can be used to send your logs to cloudwatch so you can setup alerts or other monitoring.

1. First you need to create a new log stream group in Cloudwatch that you would like to use for collecting the logs.
2. Create a new Policy in your IAM dashboard for logging access:
   1. For service, select Cloudwatch
   2. Under `List` select DescribeLogStreams
   3. Under `Write` select CreateLogStream and PutLogEvents
   4. In the Resources section, put in the ARN of the log stream group you created earlier and allow access to all streams inside of it.
3. Create a Role for your EC2 instance running Helix DAM/HTH or edit your existing role if you already have one and add permissions by attaching a Policy.
4. Attach the policy you created earlier.
5. Now that the instance can create new log streams and put log events in them, we can modify the `start_container.sh` script to add some extra lines to add the log-driver and configure our settings. (The lines starting with --log-driver and --log-opt are the new settings)  
Be sure to replace your_region_name and your_log_group_name_here with your values. (and don't forget to update the DAM_URL and ACCOUNT_KEY as before)
```bash
   docker run -d \
      --name text-thumbnail-webhook \
      --restart unless-stopped \
      --log-driver=awslogs \
      --log-opt awslogs-region=your_region_name \
      --log-opt awslogs-group=your_log_group_name \
      --log-opt awslogs-stream=text-thumbnail-webhook \
      -p 8080:8080 \
      -e DAM_URL=http://10.0.0.1 \
      -e ACCOUNT_KEY=your_account_key_here \
      text-thumbnail-webhook
```

### Other Useful Commands
- To stop the service: `docker stop text-thumbnail-webhook`
- To start a stopped service: `docker start text-thumbnail-webhook`
- To restart the service: `docker restart text-thumbnail-webhook`

### Common Issues
If you encounter issues:
1. Ensure the DAM_URL and ACCOUNT_KEY are correctly set in the `start_container.sh` script.
2. Check if the required ports are open and not used by other services.
3. Verify that Docker is running on your system.

If problems persist, review the logs for specific error messages and consult the project documentation or seek support.

[Rest of the README remains the same...]
```

This expanded section provides users with:
1. Instructions for viewing logs in different ways (all logs, real-time tailing, recent logs).
2. Commands for basic container management.
3. A brief guide on what to check if they encounter issues.

These additions will help users better monitor and troubleshoot the webhook service, enhancing their ability to maintain and manage the deployment effectively.