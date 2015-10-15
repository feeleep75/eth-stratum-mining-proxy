import binascii
import time
import struct
import subprocess
import weakref
import datetime

from twisted.internet import defer

import utils

import stratum.logger
log = stratum.logger.get_logger('proxy')

# This fix py2exe issue with packaging the midstate module
from midstate import calculateMidstate as __unusedimport

try:
    from midstatec import test as midstateTest, midstate as calculateMidstate
    if not midstateTest():
        log.warning("midstate library didn't passed self test!")
        raise ImportError("midstatec not usable")
    log.info("Using C extension for midstate speedup. Good!")
except ImportError:
    log.info("C extension for midstate not available. Using default implementation instead.")
    try:    
        from midstate import calculateMidstate
    except ImportError:
        calculateMidstate = None
        log.exception("No midstate generator available. Some old miners won't work properly.")

class Job(object):
    def __init__(self):
        self.job_id = None
        self.hexHeaderHash = ''
        self.hexSeedHash = ''
        self.hexShareTarget = ''
        self.dtCreated = datetime.datetime.now()
        self.extranonce2 = 0
        self.merkle_to_extranonce2 = {} # Relation between merkle_hash and extranonce2

    @classmethod
    def build_from_broadcast(cls, job_id, hexHeaderHash, hexSeedHash, hexShareTarget):
        '''Build job object from Stratum server broadcast'''
        job = Job()
        job.job_id = job_id
        job.hexHeaderHash = hexHeaderHash
        job.hexSeedHash = hexSeedHash
        job.hexShareTarget = hexShareTarget
        return job

    def increase_extranonce2(self):
        self.extranonce2 += 1
        return self.extranonce2

        
class JobRegistry(object):   
    def __init__(self, f, cmd, no_midstate, real_target, use_old_target=False, scrypt_target=False):
        self.f = f
        self.cmd = cmd # execute this command on new block
        self.scrypt_target = scrypt_target # calculate target for scrypt algorithm instead of sha256
        self.no_midstate = no_midstate # Indicates if calculate midstate for getwork
        self.real_target = real_target # Indicates if real stratum target will be propagated to miners
        self.use_old_target = use_old_target # Use 00000000fffffff...f instead of correct 00000000ffffffff...0 target for really old miners
        self.jobs = []        
        self.last_job = None
        self.extranonce1 = None
        self.extranonce1_bin = None
        self.extranonce2_size = None
        
        self.target = 0
        self.target_hex = ''
        self.difficulty = 1
        self.set_difficulty(1)
        self.target1_hex = self.target_hex
        
        # Relation between merkle and job
        self.merkle_to_job= weakref.WeakValueDictionary()
        
        # Hook for LP broadcasts
        self.on_block = defer.Deferred()

        self.headerHash2Job= weakref.WeakValueDictionary()

    def execute_cmd(self, prevhash):
        if self.cmd:
            return subprocess.Popen(self.cmd.replace('%s', prevhash), shell=True)

    def set_extranonce(self, extranonce1, extranonce2_size):
        self.extranonce2_size = extranonce2_size
        self.extranonce1_bin = binascii.unhexlify(extranonce1)
        
    def set_difficulty(self, new_difficulty):
        if self.scrypt_target:
            dif1 = 0x0000ffff00000000000000000000000000000000000000000000000000000000
        else:
            dif1 = 0x00000000ffff0000000000000000000000000000000000000000000000000000
        self.target = int(dif1 / new_difficulty)
        self.target_hex = binascii.hexlify(utils.uint256_to_str(self.target))
        self.difficulty = new_difficulty
        
    def build_full_extranonce(self, extranonce2):
        '''Join extranonce1 and extranonce2 together while padding
        extranonce2 length to extranonce2_size (provided by server).'''        
        return self.extranonce1_bin + self.extranonce2_padding(extranonce2)

    def extranonce2_padding(self, extranonce2):
        '''Return extranonce2 with padding bytes'''

        if not self.extranonce2_size:
            raise Exception("Extranonce2_size isn't set yet")
        
        extranonce2_bin = struct.pack('>I', extranonce2)
        missing_len = self.extranonce2_size - len(extranonce2_bin)
        
        if missing_len < 0:
            # extranonce2 is too long, we should print warning on console,
            # but try to shorten extranonce2 
            log.info("Extranonce size mismatch. Please report this error to pool operator!")
            return extranonce2_bin[abs(missing_len):]

        # This is probably more common situation, but it is perfectly
        # safe to add whitespaces
        return '\x00' * missing_len + extranonce2_bin 
    
    def add_template(self, template, clean_jobs):
        if clean_jobs:
            # Pool asked us to stop submitting shares from previous jobs
            #log.info("Start deleting old jobs")
            newJobs = []
            for job in self.jobs:  
                dtDiff = datetime.datetime.now() - job.dtCreated
                if dtDiff.total_seconds() < 300:
                    newJobs.append(job)	
            self.jobs = newJobs 					
            for job in self.jobs:  
                dtDiff = datetime.datetime.now() - job.dtCreated
                #log.info("Job %s %s " % (job.job_id, dtDiff.total_seconds()))
            
        self.jobs.append(template)
        self.last_job = template
        self.headerHash2Job[template.hexHeaderHash] = template
        
        if clean_jobs:
            # Force miners to reload jobs
            on_block = self.on_block
            self.on_block = defer.Deferred()
            on_block.callback(True)
    
            # blocknotify-compatible call
            self.execute_cmd(template.hexHeaderHash)
          
    def register_merkle(self, job, merkle_hash, extranonce2):
        # merkle_to_job is weak-ref, so it is cleaned up automatically
        # when job is dropped
        self.merkle_to_job[merkle_hash] = job
        job.merkle_to_extranonce2[merkle_hash] = extranonce2
        
    def get_job_from_header(self, header):
        '''Lookup for job and extranonce2 used for given blockheader (in hex)'''
        merkle_hash = header[72:136].lower()
        job = self.merkle_to_job[merkle_hash]
        extranonce2 = job.merkle_to_extranonce2[merkle_hash]
        return (job, extranonce2)
        
    def getwork(self):
        '''Miner requests for new getwork'''
        
        job = self.last_job # Pick the latest job from pool
          
        return [job.hexHeaderHash, job.hexSeedHash, job.hexShareTarget]            
        
    def submit(self, hexNonce, hexHeaderHash, hexMixDigest, worker_name):            
        #log.info("Submitting %s %s %s %s" % (hexHeaderHash, hexNonce, hexMixDigest, worker_name))

        try:
            job = self.headerHash2Job[hexHeaderHash]
        except KeyError:
            log.info("Job not found")
            return False
            
        return self.f.rpc('mining.submit', [worker_name, job.job_id, hexNonce, hexHeaderHash, hexMixDigest])
