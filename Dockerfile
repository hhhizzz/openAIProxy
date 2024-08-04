# Use an official Python runtime as a parent image
FROM python:3.12.4-slim

# Set the working directory in the container
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . /app

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir flask requests openai

# Make port 80 available to the world outside this container
EXPOSE 80

# Define environment variable
ENV NAME World

# Run main.py when the container launches
CMD [ "python3", "-m" , "flask", "run", "--host=0.0.0.0", "--port 80"]